"""十二步持久编排：固定脚本、真实子进程、输入输出版本、人工等待和中断恢复。"""
import argparse
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
try:
    from .pipeline_contracts import digest, atomic_batch, require_no_transaction
    from . import workflow_audit
except ImportError:
    from pipeline_contracts import digest, atomic_batch, require_no_transaction
    import workflow_audit

SCRIPTS = Path(__file__).resolve().parent
ALLOWED = (
    {'asr_capture.py', 'forced_alignment.py', 'timing_draft.py', 'timing_evidence.py', 'workflow_execution.py'},
    {'music_capture.py', 'local_perception.py', 'workbench_adoption.py'},
    {'reference_roles.py'},
    {'organization_workflow.py', 'film_grammar_bridge.py', 'storyboard_build.py', 'visual_development.py', 'sequence_direction.py', 'crew_pipeline.py', 'crew_rehearsal.py'},
    {'prompt_build.py', 'chapter_plan_build.py', 'chapter_audio_build.py', 'chapter_prompt_build.py', 'render_preview.py', 'animatic_review.py', 'workflow_execution.py'},
    {'workflow_execution.py'},
    {'visual_assets.py', 'director_review_gate.py'},
    {'batch_scheduler.py'},
    {'repair_state.py', 'local_transform.py'},
    {'edit_assemble.py', 'stitch_chapters.py', 'director_review_gate.py'},
    {'stitch_chapters.py', 'delivery_package.py', 'delivery_state.py', 'lip_measure.py'},
    {'release_evidence.py'},
)


def encode(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)


def local(project, name):
    path = (project/name).resolve()
    path.relative_to(project)
    return path


def snapshot(project, paths):
    return {str(local(project, p)): digest(local(project, p)) for p in paths}


def current_outputs(row, records):
    """保留历史实际输出；同一文件由后续已完成步骤显式接管时按最后写入者核验。"""
    expected = dict(row.get('outputs', {}))
    for later in sorted(records.values(),key=lambda r:r['step']):
        if later['step'] > row['step'] and later.get('status') == 'completed':
            for name,value in later.get('outputs',{}).items():
                if name in expected: expected[name] = value
    return expected


def inspect(project, plan_path):
    """只读核验持久记录，不能补造一次命令执行。"""
    project, plan_path = Path(project).resolve(), Path(plan_path).resolve()
    plan = json.loads(plan_path.read_text(encoding='utf8'))
    path = project/'state/workflow_run.json'
    old = json.loads(path.read_text(encoding='utf8')) if path.is_file() else {}
    if old.get('plan_sha256') != digest(plan_path):
        return {'status':'waiting_execution','steps':[],'error':'没有与当前计划一致的实际执行记录'}
    records = {r['step']:r for r in old['steps']}
    errors = []
    for index,stage in enumerate(plan['steps'],1):
        try:
            row = records.get(index,{})
            if (row.get('status') != 'completed' or row.get('inputs') != snapshot(project,stage.get('inputs',[]))
                    or current_outputs(row,records) != snapshot(project,stage['outputs'])
                    or row.get('code') != {str(p):digest(p) for p in SCRIPTS.glob('*.py')}):
                raise ValueError('步骤缺少当前有效的完成记录')
            errors.extend(f'步骤{index}: '+e for e in check_step(project,index,plan))
        except Exception as exc:
            errors.append(f'步骤{index}: {exc}')
    return {'status':'blocked' if errors else 'completed','steps':old.get('steps',[]),'errors':errors}


def check_step(project, index, plan):
    if index == 2:
        try:
            review = json.loads((project/'state/style_review.json').read_text(encoding='utf8'))
            if (review.get('decision') != 'approve' or not str(review.get('observer', '')).strip()
                    or not str(review.get('evidence', '')).strip()
                    or review.get('style_sha256') != digest(project/'state/style.json')
                    or review.get('music_sha256') != digest(project/'state/music_structure.json')):
                return ['音乐与导演风格尚未获当前版本的人工复核']
            return []
        except Exception as exc:
            return ['音乐与导演风格待核: '+str(exc)]
    if index == 3:
        try:
            try:
                from .reference_roles import require as require_roles
            except ImportError:
                from reference_roles import require as require_roles
            require_roles(project)
            return []
        except Exception as exc:
            return ['人物原图/上传职责未通过: '+str(exc)]
    phase = 'before-generation' if index <= 6 else 'before-batch' if index <= 8 else 'before-delivery'
    report = workflow_audit.audit(project, phase=phase, submission=local(project, plan['submission']) if plan.get('submission') else None,
                                  output_name=plan.get('output_name', 'final_mv.mp4'))
    ids = set(workflow_audit.STEPS[index-1][1]) - {'execution_receipts'}
    # 剧组当前报告依赖gate5编译的提示词指纹，在第5步一并重验，避免先后依赖循环。
    if index == 4: ids.discard('crew_reports')
    if index == 5: ids.add('crew_reports')
    checks = [c for c in report['checks'] if c['id'] in ids]
    errors = [e for c in checks if c['status'] == 'blocked' for e in c['errors']]
    if index == 4 and plan.get('creative_workflow', {}).get('film_grammar_required') is True:
        try:
            try:
                from .film_grammar_bridge import require as require_organization
            except ImportError:
                from film_grammar_bridge import require as require_organization
            require_organization(project, required=True)
        except Exception as exc:
            errors.append('电影镜头组织交接未完成: '+str(exc))
    # 批量阶段必须消费当前已完成的队列，不把合法提交契约当实际生成。
    if index == 8:
        try:
            try:
                from .batch_scheduler import require_completed
            except ImportError:
                from batch_scheduler import require_completed
            require_completed(project)
        except Exception as exc:
            errors.append(str(exc))
    if index == 11:
        sb = json.loads((project/'state/storyboard.json').read_text(encoding='utf8'))
        if any(s['lip_sync'] for s in sb['shots']):
            try:
                try:
                    from .lip_measure import require as require_lip
                except ImportError:
                    from lip_measure import require as require_lip
                require_lip(project)
            except Exception as exc:
                errors.append('十二步完成要求独立口型测量: '+str(exc))
    return errors


def run(project, plan_path, *, execute=True):
    project = Path(project).resolve()
    require_no_transaction(project)
    plan_path = Path(plan_path).resolve()
    plan_sha = digest(plan_path)
    plan = json.loads(plan_path.read_text(encoding='utf8'))
    if plan.get('project_id') != str(project) or len(plan.get('steps', [])) != 12:
        raise ValueError('执行计划须绑定本项目且列出十二步')
    # 在产生任何副作用前完整验证命令和路径。
    for i, stage in enumerate(plan['steps']):
        if stage.get('step') != i+1 or not stage.get('outputs'):
            raise ValueError('步骤须按1至12排列并声明实际输出')
        for p in stage.get('inputs', []) + stage['outputs']: local(project, p)
        for command in stage.get('commands', []):
            if (not isinstance(command, list) or not command or command[0] not in ALLOWED[i]
                    or any(not isinstance(arg, str) for arg in command)):
                raise ValueError('命令未在当前步骤允许集合中')
            if not any('{project}' in arg for arg in command[1:]):
                raise ValueError('命令须显式使用{project}绑定当前项目')
            if any(arg in ('--help', '-h', '--version') for arg in command):
                raise ValueError('帮助命令不能充作执行')
    policy = plan.get('creative_workflow', {})
    if not isinstance(policy, dict) or ('film_grammar_required' in policy and type(policy['film_grammar_required']) is not bool):
        raise ValueError('creative_workflow.film_grammar_required须为布尔值')
    if 'organization_order' in policy and (type(policy['organization_order']) is not int or policy['organization_order'] not in (1,2)):
        raise ValueError('organization_order须为1或2')
    if policy.get('organization_order') == 2 and policy.get('film_grammar_required') is not True:
        raise ValueError('严格组织顺序必须启用film_grammar_required')
    if not execute:
        return inspect(project,plan_path)
    path = project/'state/workflow_run.json'
    lock = project/'.workflow-run.lock'
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        os.write(fd, encode({'pid': os.getpid()}).encode())
        # 独立CLI也消费项目策略，不能通过跳过十二步入口绕过组织交接。
        policy_path = project/'state/creative_workflow.json'
        if policy.get('film_grammar_required') is True:
            wanted = {'film_grammar_required': True, 'reference_mode': 'creative_advisory', 'organization_order': policy.get('organization_order', 1)}
            policy_version = digest(policy_path) if policy_path.is_file() else None
            if policy_path.is_file() and json.loads(policy_path.read_text(encoding='utf8')).get('organization_order') == 2:
                wanted['organization_order'] = 2
            if not policy_path.is_file() or json.loads(policy_path.read_text(encoding='utf8')) != wanted:
                atomic_batch({policy_path: encode(wanted)}, expected={policy_path: policy_version, plan_path: plan_sha})

        old = json.loads(path.read_text(encoding='utf8')) if path.is_file() else {}
        state = old if old.get('plan_sha256') == plan_sha else {'schema_version': 1, 'project_id': str(project), 'plan_sha256': plan_sha, 'steps': []}
        version = digest(path) if path.is_file() else None
        def save():
            nonlocal version
            atomic_batch({path: encode(state)}, expected={path: version, plan_path: plan_sha})
            version = digest(path)
        records = {row['step']: row for row in state['steps']}
        state['status'] = 'running'
        for index, stage in enumerate(plan['steps'], 1):
            row = records.get(index)
            try:
                cached = (row is not None and row['status'] == 'completed'
                          and row['inputs'] == snapshot(project, stage.get('inputs', []))
                          and current_outputs(row,records) == snapshot(project, stage['outputs'])
                          and row['code'] == {str(p): digest(p) for p in SCRIPTS.glob('*.py')}
                          and not check_step(project, index, plan))
            except (OSError, ValueError, KeyError):
                cached = False
            if cached: continue
            # 已持久记录running的命令可能已有外部副作用；恢复只核验产物，绝不自动重派。
            interrupted = bool(row and (row.get('status') == 'running' or row.get('recovery_required')))
            state['steps'] = [r for r in state['steps'] if r['step'] < index]
            row = {'step': index, 'status': 'running', 'run_id': uuid.uuid4().hex, 'processes': [], 'inputs': {},
                   'recovery_required': interrupted}
            state['steps'].append(row)
            save()
            try:
                row['inputs'] = snapshot(project, stage.get('inputs', []))
                code = {str(p): digest(p) for p in SCRIPTS.glob('*.py')}
                commands = stage.get('commands', [])
                if commands and not execute and not interrupted:
                    raise ValueError('步骤尚未实际运行；check不能以现有输出替代所声明的命令执行')
                if execute and not interrupted:
                    for command in commands:
                        args = [sys.executable, str(SCRIPTS/command[0]), *[arg.replace('{project}', str(project)) for arg in command[1:]]]
                        row['active_command'] = args
                        save()
                        result = subprocess.run(args, cwd=SCRIPTS.parent, capture_output=True, text=True, encoding='utf8', errors='replace')
                        row['processes'].append({'command': args, 'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr})
                        save()
                        if result.returncode:
                            raise ValueError('实际步骤命令失败，修正后重新resume')
                errors = check_step(project, index, plan)
                outputs = snapshot(project, stage['outputs'])
                if errors: raise ValueError('; '.join(errors))
                if row['inputs'] != snapshot(project, stage.get('inputs', [])) or code != {str(p): digest(p) for p in SCRIPTS.glob('*.py')}:
                    raise ValueError('步骤期间输入或代码改变；输入与输出须分别声明')
                row.update(status='completed', outputs=outputs, code=code)
                row.pop('active_command', None)
                save()
            except Exception as exc:
                row.update(status='waiting_review' if not stage.get('commands') or interrupted else 'failed', error=str(exc))
                state['status'] = row['status']
                save()
                return state
        state['status'] = 'completed'
        save()
        return state
    finally:
        os.close(fd)
        lock.unlink(missing_ok=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('run', 'resume', 'check'))
    parser.add_argument('project', type=Path)
    parser.add_argument('--plan', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.project, args.plan, execute=args.action != 'check')
    print(encode(result))
    raise SystemExit(0 if result['status'] == 'completed' else 1)
