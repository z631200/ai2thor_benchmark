# robot_interface.py
import ai2thor.controller
from typing import Any, Dict, Optional
import math
import json
import time

class RobotInterface:
    dic_objloc = {
        "knife": [-1, 0.9, -0.25],
        "potato": [-1, 0.9, -1.5],
        "sink": [-1, 0.9, -1.5],
        "microwave": [-0.25, 0.9, -1.25],
        "bowl": [0.25, 0.9, -1.25],
        "final": [0.25, 0.9, -1.25],
    }

    def __init__(self, controller, frame_hook=None):
        self.controller = controller
        self.frame_hook = frame_hook

    def _after_step(self, event):
        # 每次 controller.step 後呼叫，讓外部決定要不要錄影
        if callable(self.frame_hook):
            frame = getattr(event, "frame", None)
            if frame is not None:
                self.frame_hook(frame)

    # ---------- 新增：target 自動解析（名稱 -> objectId）----------

    @staticmethod
    def _is_thor_object_id(s: Any) -> bool:
        """
        AI2-THOR 的 objectId 通常會包含 '|' 分隔符。
        例如: 'Potato|+01.23|+00.90|-01.58'
        """
        return isinstance(s, str) and ("|" in s)

    @staticmethod
    def _sq_dist(a: Dict[str, float], b: Dict[str, float]) -> float:
        dx = (a.get("x", 0.0) - b.get("x", 0.0))
        dy = (a.get("y", 0.0) - b.get("y", 0.0))
        dz = (a.get("z", 0.0) - b.get("z", 0.0))
        return dx * dx + dy * dy + dz * dz

    @staticmethod
    def _is_interactable_for_action(obj: Dict[str, Any], action_cmd: str) -> bool:
        """
        依 action 判斷「可互動」：避免選到可見但不可執行該動作的物件。
        """
        action_cmd = action_cmd

        if action_cmd in ("OpenObject", "CloseObject"):
            return bool(obj.get("openable", False))
        if action_cmd == "PickupObject":
            return bool(obj.get("pickupable", False))
        if action_cmd == "ToggleObjectOn":
            return bool(obj.get("toggleable", False))
        if action_cmd == "SliceObject":
            return bool(obj.get("sliceable", False))
        if action_cmd == "PutObject":
            # PutObject 若指定 target，我們用 PutObject -> target 必須是 receptacle
            return bool(obj.get("receptacle", False))

        # 其他動作預設不做限制（或你可視需求加強）
        return True

    @staticmethod
    def _sq_screen_dist(
        sp: Dict[str, float],
        center_x: float,
        center_y: float,
    ) -> float:
        dx = (sp.get("x", 0.0) - center_x)
        dy = (sp.get("y", 0.0) - center_y)
        return dx * dx + dy * dy

    def _resolve_target_object_id(
        self,
        target_name: str,
        action_cmd: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        在「當前視野可見」且「可對該 action 互動」的物件中，
        找到 objectType == target_name 的候選；若多個，選「距離畫面中心最近」者。
        - 優先使用 obj["screenPosition"] 的 (x,y) 與畫面中心做 2D 距離
        - 若缺少 screenPosition，fallback 使用原本的 Agent 3D 距離
        """
        if not isinstance(target_name, str) or not target_name:
            return None

        metadata = metadata or self.controller.last_event.metadata
        objects = metadata.get("objects", [])
        agent_pos = metadata.get("agent", {}).get("position", {})

        name_norm = target_name.strip().lower()

        candidates = []
        for obj in objects:
            if obj.get("objectType", "").lower() != name_norm:
                continue
            if not obj.get("visible", False):
                continue
            if not self._is_interactable_for_action(obj, action_cmd):
                continue
            if not obj.get("objectId"):
                continue
            candidates.append(obj)

        if not candidates:
            return None

        # --- 決定畫面中心座標（支援 normalized 或 pixel） ---
        # 1) 先嘗試用 frame 尺寸（最可靠）
        frame = getattr(self.controller.last_event, "frame", None)
        frame_w = frame.shape[1] if frame is not None and hasattr(frame, "shape") else None
        frame_h = frame.shape[0] if frame is not None and hasattr(frame, "shape") else None

        # 2) 如果拿不到 frame，就先假設 normalized center (0.5, 0.5)
        #    若遇到 pixel 座標，我們會在排序 key 裡自動判斷並改用 W/2,H/2（若 W/H 可得）
        norm_center = (0.5, 0.5)

        def sort_key(o: Dict[str, Any]) -> float:
            sp = o.get("screenPosition")
            if isinstance(sp, dict) and ("x" in sp) and ("y" in sp):
                x = float(sp.get("x", 0.0))
                y = float(sp.get("y", 0.0))

                # 判斷 screenPosition 是 normalized 還是 pixel：
                # - 大多數情況 normalized 會落在 [0,1]
                # - pixel 則通常 > 1
                is_normalized = (0.0 <= x <= 1.5) and (0.0 <= y <= 1.5)

                if is_normalized:
                    cx, cy = norm_center
                    return self._sq_screen_dist({"x": x, "y": y}, cx, cy)

                # pixel：若有 frame 尺寸就用中心點 (W/2, H/2)，否則退回用 normalized center 的縮放近似
                if frame_w is not None and frame_h is not None:
                    cx, cy = frame_w / 2.0, frame_h / 2.0
                    return self._sq_screen_dist({"x": x, "y": y}, cx, cy)

                # frame 尺寸不可得：保守 fallback（避免除零/亂猜），改用 agent distance
                return self._sq_dist(agent_pos, o.get("position", {}))

            # 沒有 screenPosition：fallback 使用 agent distance
            return self._sq_dist(agent_pos, o.get("position", {}))

        candidates.sort(key=sort_key)
        return candidates[0].get("objectId")


    # ---------- 新增：PutObject 兼容呼叫（不同 THOR 版本參數差異）----------

    def _put_object_compat(self, receptacle_id: str):
        """
        兼容不同 AI2-THOR 版本的 PutObject 參數：
        - 新版常見：PutObject(objectId=...)
        - 舊版常見：PutObject(receptacleObjectId=...)
        會先嘗試 objectId，若回報參數錯誤再 fallback。
        """
        # 先試 objectId 版本
        try:
            ev = self.controller.step(
                action="PutObject",
                objectId=receptacle_id,
                forceAction=False,
            )
            if ev.metadata.get("lastActionSuccess", False):
                return ev

            msg = (ev.metadata.get("errorMessage") or "")
            if "invalid argument" not in msg:
                return ev
        except Exception:
            pass

        # fallback：receptacleObjectId 版本
        return self.controller.step(
            action="PutObject",
            receptacleObjectId=receptacle_id,
            forceAction=False,
        )

    # ---------- 原本 parse_and_execute：加上自動解析 ----------

    def parse_and_execute(self, action_cmd: str, target: Any = None):
        """
        執行動作。
        支援動作: MoveAhead, RotateLeft/right, LookUp/down, Teleport,
                 OpenObject, CloseObject, PickupObject, ToggleObjectOn, SliceObject, PutObject

        新增能力：
        - 若 target 是 objectType 名稱（如 'Potato'），會自動在可見且可互動的物件中找最近者，轉成 objectId 後執行。
        - PutObject 支援：
          * target=None：DropHandObject（丟地板）
          * target="center"：PutObject(x=0.5,y=0.5,putNearXY=True)（放到畫面中心附近）
          * target={"x":0~1,"y":0~1}：PutObject(x,y,putNearXY=True)（放到指定螢幕座標附近）
          * target=receptacle 的 objectId 或 objectType 名稱：PutObject 到 receptacle
        """
        action_cmd = action_cmd
        event = None

        try:
            # --- 導航動作 ---
            if action_cmd  == "Done":
                event = self.controller.step(action="Done")
        
            elif action_cmd  == "Stand":
                event = self.controller.step(action="Stand")

            elif action_cmd in ["MoveAhead", "MoveBack"]:
                if target==None:
                    target = 0.25
                event = self.controller.step(action=action_cmd, moveMagnitude=target)
                    

            elif action_cmd in ["RotateRight", "RotateLeft"]:
                if target is None:
                    target = 90

                total = float(target)
                total = abs(total)

                step_deg = 30
                remaining = total

                while remaining > 1e-6:
                    d = min(step_deg, remaining)
                    event = self.controller.step(action=action_cmd, degrees=d)
                    self._after_step(event)
                    time.sleep(0.05)
                    if not event.metadata.get("lastActionSuccess", False):
                        break
                    remaining -= d                   


            elif action_cmd in ["LookUp", "LookDown"]:
                if target == None:
                    target = 30
                total = float(target)
                total = abs(total)

                step_deg = 15.0
                remaining = total

                while remaining > 1e-6:
                    d = min(step_deg, remaining)
                    event = self.controller.step(action=action_cmd, degrees=d)
                    self._after_step(event)
                    time.sleep(0.05)
                    if not event.metadata.get("lastActionSuccess", False):
                        break
                    remaining -= d   


            elif action_cmd == "Teleport":
                position = None
                # 情況 A: target 是座標字典
                if isinstance(target, dict) and "x" in target:
                    position = target
                # 情況 B: target 是字串且在 dic_objloc
                elif isinstance(target, str) and target in self.dic_objloc:
                    coords = self.dic_objloc[target]
                    position = {"x": coords[0], "y": coords[1], "z": coords[2]}
                else:
                    return {
                        "success": False,
                        "message": f"Teleport 失敗: target '{target}' 無效或不在 dic_objloc 中",
                    }
                event = self.controller.step(action="Teleport", position=position)

            # --- 互動動作：先把 target 名稱解析為 objectId（若需要） ---
            elif action_cmd in ["PutObject", "OpenObject", "CloseObject", "PickupObject", "ToggleObjectOn", "SliceObject", "ToggleObjectOff"]:

                # PutObject 的特殊 target（center / 螢幕座標）要先攔截，避免被當成 objectType 去 resolve
                if action_cmd == "PutObject":
                    # 1) 放到畫面中心
                    if target == "center":
                        event = self.controller.step(
                            action="PutObject",
                            x=0.5,
                            y=0.5,
                            forceAction=False,
                            putNearXY=True,
                        )
                        return {
                            "success": event.metadata.get("lastActionSuccess", False),
                            "message": event.metadata.get("errorMessage", ""),
                        }

                    # 2) 放到指定螢幕座標（0~1），例如 {"x":0.5,"y":0.5}
                    if isinstance(target, dict) and ("x" in target) and ("y" in target) and ("z" not in target):
                        event = self.controller.step(
                            action="PutObject",
                            x=float(target["x"]),
                            y=float(target["y"]),
                            forceAction=False,
                            putNearXY=True,
                        )
                        return {
                            "success": event.metadata.get("lastActionSuccess", False),
                            "message": event.metadata.get("errorMessage", ""),
                        }

                # 如果 target 是字串但不像 objectId，視為 objectType 名稱，嘗試解析成 objectId
                if isinstance(target, str) and (not self._is_thor_object_id(target)):
                    resolved = self._resolve_target_object_id(
                        target_name=target,
                        action_cmd=action_cmd,
                        metadata=self.controller.last_event.metadata,
                    )
                    if resolved is None:
                        return {
                            "success": False,
                            "message": f"找不到可見且可互動的物件: '{target}' (action={action_cmd})",
                        }
                    target = resolved

                if action_cmd == "PutObject":
                    # 有 target（receptacle 的 objectId）：PutObject；否則 DropHandObject
                    if isinstance(target, str) and self._is_thor_object_id(target):
                        event = self._put_object_compat(target)
                    else:
                        event = self.controller.step(action="DropHandObject")
                
                # 修改 robot_interface.py 中的 OpenObject 區段

                elif action_cmd == "OpenObject":
                    # 1. 確保 target 已解析為 objectId
                    if isinstance(target, str) and (not self._is_thor_object_id(target)):
                        target = self._resolve_target_object_id(target, action_cmd)
                    
                    if target:
                        # 2. 定義動畫參數
                        steps = 5  # 分成 10 步打開
                        for i in range(1, steps + 1):
                            fraction = i / steps
                            # 呼叫 OpenObject 並指定開啟幅度 (0.0 ~ 1.0)
                            event = self.controller.step(
                                action=action_cmd,
                                objectId=target,
                                openness=fraction, # 指定開啟比例
                                forceAction=False
                            )
                            self._after_step(event)
                            time.sleep(0.05)
                            # 如果某一步失敗，則停止
                            if not event.metadata.get("lastActionSuccess", False):
                                break
                            # 這裡可以選擇是否加一點微小的延遲，
                            # 但 controller.step 執行本身就有耗時，通常已有動畫感。
                    else:
                        # 若無 target，則對畫面中心執行一次性開啟
                        event = self.controller.step(action="OpenObject", x=0.5, y=0.5)

                else:
                    thor_action = {
                        "OpenObject": "OpenObject",
                        "CloseObject": "CloseObject",
                        "PickupObject": "PickupObject",
                        "ToggleObjectOn": "ToggleObjectOn",
                        "ToggleObjectOff": "ToggleObjectOff",
                        "SliceObject": "SliceObject",
                    }[action_cmd]

                    if isinstance(target, str) and self._is_thor_object_id(target):
                        event = self.controller.step(action=thor_action, objectId=target)
                    else:
                        # 未指定 target：操作畫面中心
                        print(f"[System] 未指定 Target ID，嘗試對畫面中心執行 {thor_action}")
                        event = self.controller.step(action=thor_action, x=0.5, y=0.5)

            elif action_cmd == "ShowDetail":
                if not isinstance(target, str) or not target.strip():
                    return {"success": False, "message": "ShowDetail 失敗: target 必須是物件名稱(如 'bowl')"}

                name_norm = target.strip().lower()
                objects = self.controller.last_event.metadata.get("objects", [])

                matched = [o for o in objects if o.get("objectType", "").lower() == name_norm]

                if not matched:
                    print(f"[ShowDetail] 找不到 objectType == {target} 的物件")
                    return {"success": False, "message": f"ShowDetail: 找不到物件類型 {target}"}

                print(f"[ShowDetail] objectType == {target} 的物件共有 {len(matched)} 個：")
                for i, obj in enumerate(matched, 1):
                    print(f"\n--- {target} #{i} ---")
                    print(json.dumps(obj, ensure_ascii=False, indent=2))

                return {"success": True, "message": ""}


            else:
                return {"success": False, "message": f"未知的動作: {action_cmd}"}

            return {
                "success": event.metadata.get("lastActionSuccess", False),
                "message": event.metadata.get("errorMessage", ""),
            }

        except Exception as e:
            return {"success": False, "message": f"系統錯誤: {str(e)}"}
