import json
import time
import os
import cv2
from robot_interface import RobotInterface
from benchmark_referee import Referee
from task_definition import TaskDefinition

class Logger:
    def __init__(self, filepath="trace_log.json"):
        self.filepath = filepath
        self.history = []

    def log_step(self, step, action, target, result, referee_msg, goal_status):
        self.history.append({
            "step": step,
            "timestamp": time.time(),
            "action": action,
            "target": target,
            "success": result["success"],
            "error_message": result["message"],
            "referee_feedback": referee_msg,
            "goal_status": goal_status
        })

    def save(self):
        with open(self.filepath, 'w', encoding='utf-8') as f:
            json.dump(self.history, f, indent=4, ensure_ascii=False)
        print(f"[Logger] 紀錄已儲存至 {self.filepath}")

class SimulationPlatform:
    def __init__(self, controller, record_video: bool = False, video_path: str = "run.mp4", fps: int = 5):
        self.controller = controller
        self.robot = RobotInterface(controller)
        self.referee = Referee()
        self.logger = Logger()
        self.current_task = None
        self.step_count = 0

        # ✅ 錄影相關
        self.record_video = record_video
        self.video_path = video_path
        self.fps = fps
        self._video_writer = None

    def _init_video_writer_if_needed(self):
        """在拿得到 frame 尺寸後才初始化 VideoWriter（避免不知道 width/height）"""
        if (not self.record_video) or (self._video_writer is not None):
            return

        frame = self.controller.last_event.frame
        if frame is None:
            return

        h, w = frame.shape[:2]
        os.makedirs(os.path.dirname(self.video_path) or ".", exist_ok=True)

        # mp4 常用編碼（有些環境用 mp4v 最穩）
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self._video_writer = cv2.VideoWriter(self.video_path, fourcc, self.fps, (w, h))

        if not self._video_writer.isOpened():
            raise RuntimeError(f"VideoWriter 無法開啟：{self.video_path}")

        print(f"[Video] 開始錄影：{self.video_path} ({w}x{h}, fps={self.fps})")

    def load_task(self, task: TaskDefinition):
        self.current_task = task
        print(f"[Platform] 載入任務: {task.instruction}")
        self.controller.reset(scene=task.scene_id)
        self.step_count = 0

        # ✅ reset 後通常就有 last_event.frame，可在這裡初始化
        if self.record_video:
            self._init_video_writer_if_needed()

    def run_step(self, action: str, target_id: str = None):
        """AI 呼叫此函式來執行一步"""
        self.step_count += 1

        # 1. Robot 執行
        result = self.robot.parse_and_execute(action, target_id)

        # 2. 取得最新環境資料
        metadata = self.controller.last_event.metadata

        # ✅ 錄影：確保 writer 已初始化，然後寫入這一幀
        if self.record_video:
            self._init_video_writer_if_needed()
            frame = self.controller.last_event.frame
            if frame is not None and self._video_writer is not None:
                # AI2-THOR frame 通常是 RGB；OpenCV 期待 BGR
                self._video_writer.write(frame[:, :, ::-1])

        # 3. Referee 判定
        step_feedback = self.referee.evaluate_step(result)
        task_status = self.referee.check_success(self.current_task, metadata)

        # 4. 紀錄
        self.logger.log_step(self.step_count, action, target_id, result, step_feedback, task_status)

        # 5. 回傳
        return {
            "image": self.controller.last_event.frame,
            "feedback": step_feedback,
            "task_done": task_status["is_success"],
            "goal_details": task_status["details"]
        }

    def finish(self):
        # ✅ 先釋放影片（確保 mp4 完整寫入）
        if self._video_writer is not None:
            self._video_writer.release()
            self._video_writer = None
            print(f"[Video] 錄影完成：{self.video_path}")

        self.logger.save()