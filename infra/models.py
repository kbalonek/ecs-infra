from dataclasses import dataclass
from pathlib import Path


@dataclass
class MonorepoApp:
    path: Path
    django_debug: bool
    app_task_memory_mib: int
    app_task_desired_count: int
    app_task_min_scaling_capacity: int
    app_task_max_scaling_capacity: int
    worker_task_min_scaling_capacity: int
    worker_task_max_scaling_capacity: int
    worker_scaling_steps: list


@dataclass
class PolyramaApp:
    name: str
    subdomain_name: str
    monorepo_app: MonorepoApp
