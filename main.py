# main.py
import time
from ai2thor.controller import Controller
from task_definition import TaskDefinition
from simulation_platform import SimulationPlatform

def find_object_id_by_type(controller, obj_type):
    for obj in controller.last_event.metadata['objects']:
        if obj['objectType'] == obj_type:
            return obj['objectId']
    return None

def customize_env(controller):
    knife_id = find_object_id_by_type(controller, 'Knife')  
    if not knife_id:
        print("找不到 Knife")
    else:
        target_pos = {"x": -1.7018153667449951, "y": 0.899, "z": -0.2227991670370102}
        target_rot = {"x": 0.00015026416804175824, "y": 136.23866271972656, "z": 89.99844360351562}

        try:
            ev = controller.step(
                action="TeleportObject",
                objectId=knife_id,
                position=target_pos,
                rotation=target_rot,
                forceAction=False,
            )

            print(f"TeleportObject success =", ev.metadata.get("lastActionSuccess", False))
            if not ev.metadata.get("lastActionSuccess", False):
                print("error =", ev.metadata.get("errorMessage", ""))
        except Exception as e:
            print("[customize_env] TeleportObject exception:", str(e))

def main():
    print('正在啟動 AI2-THOR...')
    controller = Controller(width=600, height=600)
    RECORD_VIDEO = True
    platform = SimulationPlatform(
        controller,
        record_video=RECORD_VIDEO,
        video_path="./run.mp4",
        fps=8
    )

    task = TaskDefinition('task_cook_potato', 'FloorPlan1', 'Cook a potato')

    # ALFRED-style PDDL goal (subset evaluator)
    goal_pddl = r"""
    (:goal
        (and
            (forall (?re # receptacle)
                (not (opened ?re))
            )
            (exists (?r # receptacle)
                (and
                    (receptacleType ?r BowlType)
                    (exists (?ct # receptacle)
                        (and
                            (receptacleType ?ct CounterTopType)
                            (inReceptacle ?r ?ct)
                        )
                    )
                )
            )
            (exists (?r # receptacle)
                (exists (?o # object)
                    (and
                        (receptacleType ?r BowlType)
                        (objectType ?o PotatoSlicedType)
                        (inReceptacle ?o ?r)
                        (isCooked ?o True)
                    )
                )
            )
        )
    )
    """
    task.set_goal_pddl(goal_pddl)

    platform.load_task(task)
    print('\n--- 開始執行任務 ---')

    potato_id = find_object_id_by_type(controller, 'Potato')
    microwave_id = find_object_id_by_type(controller, 'Microwave')
    # customize_env(controller)

    if not potato_id or not microwave_id:
        print('錯誤: 場景中找不到 Potato 或 Microwave，請重試 (隨機生成問題)')
        platform.finish()
        return

    action_plan = [
        ('ShowDetail', 'bowl'),
        ('Wait', 1),
        # ('Teleport', 'knife'),
        ('RotateLeft', 90),
        ('MoveAhead', 0.25),
        ('MoveAhead', 0.25),
        ('MoveAhead', 0.25),
        ('MoveAhead', 0.25),
        ('LookDown', 15),
        ('LookDown', 15),
        ('RotateRight', 45),
        ('OpenObject', 'drawer'),
        ('ShowDetail', 'knife'),
        # ('MoveBack', None),
        ('PickupObject', 'knife'),
        ('CloseObject', 'drawer'),
        # ('Teleport', 'potato'),
        ('RotateLeft', 45),
        ('MoveAhead', 0.25),
        ('MoveAhead', 0.25),
        ('MoveAhead', 0.25),
        ('MoveAhead', 0.25),
        ('MoveAhead', 0.25),
        ('MoveAhead', 0.25),
        ('RotateRight', 45),
        ('SliceObject', 'potato'),        
        ('PutObject', 'CounterTop'),
        # ('Teleport', 'bowl'),
        ('RotateLeft', 135),
        ('MoveAhead', 0.25),
        ('MoveAhead', 0.25),
        ('MoveAhead', 0.25),
        ('MoveAhead', 0.25),
        ('RotateLeft', 90),
        ('PickupObject', 'bowl'),
        # ('Teleport', 'potato'),
        ('RotateLeft', 90),
        ('MoveAhead', 0.25),
        ('MoveAhead', 0.25),
        ('MoveAhead', 0.25),
        ('MoveAhead', 0.25),
        ('RotateLeft', 45),
        ('MoveAhead', 0.25),
        ('PutObject', 'CounterTop'),
        ('PickupObject', 'PotatoSliced'),
        ('PutObject', 'bowl'),
        ('PickupObject', 'PotatoSliced'),
        ('PutObject', 'bowl'),
        ('PickupObject', 'PotatoSliced'),
        ('PutObject', 'bowl'),
        ('PickupObject', 'bowl'),
        # ('Teleport', 'microwave'),
        ('RotateLeft', 135),
        ('MoveAhead', 0.25),
        ('MoveAhead', 0.25),
        ('MoveAhead', 0.25),
        ('MoveAhead', 0.25),
        ('RotateRight', 90),
        ('LookUp', 15),
        ('LookUp', 15),
        ('OpenObject', 'microwave'),
        ('PutObject', 'microwave'),
        ('CloseObject', 'microwave'),
        ('ToggleObjectOn', 'microwave'),
        ('Wait', 1),
        ('ToggleObjectOff', 'microwave'),
        ('OpenObject', 'microwave'),
        ('PickupObject', 'bowl'),
        ('CloseObject', 'microwave'),
        # ('Teleport', 'final'),
        ('RotateLeft', 135),
        ('MoveAhead', 0.25),
        ('RotateLeft', 45),
        ('PutObject', 'CounterTop'),
        ('MoveBack', 0.25),
        ('Wait', 1),
        ('Done', None),
    ]

    post_success_steps = 3   # 成功後多跑幾步以觀察結果
    success_seen = False
    remaining = 0

    for action, target in action_plan:
        print(f"\n[Agent] 執行: {action} target={target}")
        obs = platform.run_step(action, target)
        print(f" > 平台回饋: {obs['feedback']}")
        print(f" > 任務狀態: {obs['goal_details']}")

        if obs['task_done'] and not success_seen:
            success_seen = True
            remaining = post_success_steps
            print(f"\n*** goal achieved: will continue {post_success_steps} more steps for rendering ***")

        if success_seen:
            remaining -= 1
            if remaining <= 0:
                print("\n*** task done (after extra steps) ***")
                break

        time.sleep(2)


    time.sleep(3)
    platform.finish()

if __name__ == '__main__':
    main()
