"""Dados iniciais: a linha `LINE-01` descrita em `docs/01-planejamento.md`."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.models import Machine, User
from app.models.enums import MachineStatus, MachineType, UserRole

logger = logging.getLogger(__name__)

#: Catálogo da linha. Cada entrada vira uma linha em `machines`.
MACHINE_CATALOG: list[dict] = [
    {
        "code": "INJ-01",
        "name": "Injetora de Plástico",
        "machine_type": MachineType.INJECTOR,
        "sequence": 1,
        "pos_x": 10.0,
        "pos_y": 60.0,
        "ideal_cycle_time_s": 8.0,
        "temp_nominal": 195.0,
        "temp_warning": 215.0,
        "temp_critical": 230.0,
        "speed_nominal": 45.0,
        "speed_min": 30.0,
        "speed_max": 60.0,
        "vib_warning": 3.5,
        "vib_critical": 5.6,
        "pressure_nominal": 120.0,
        "pressure_max": 160.0,
        "energy_nominal": 68.0,
    },
    {
        "code": "CNV-01",
        "name": "Esteira Transportadora",
        "machine_type": MachineType.CONVEYOR,
        "sequence": 2,
        "pos_x": 30.0,
        "pos_y": 60.0,
        "ideal_cycle_time_s": 4.0,
        "temp_nominal": 38.0,
        "temp_warning": 55.0,
        "temp_critical": 68.0,
        "speed_nominal": 22.0,
        "speed_min": 14.0,
        "speed_max": 30.0,
        "vib_warning": 4.5,
        "vib_critical": 7.1,
        "pressure_nominal": 0.0,
        "pressure_max": 2.0,
        "energy_nominal": 6.5,
    },
    {
        "code": "ROB-01",
        "name": "Braço Robótico Pega-e-Posiciona",
        "machine_type": MachineType.ROBOT,
        "sequence": 3,
        "pos_x": 50.0,
        "pos_y": 60.0,
        "ideal_cycle_time_s": 5.0,
        "temp_nominal": 46.0,
        "temp_warning": 62.0,
        "temp_critical": 75.0,
        "speed_nominal": 780.0,
        "speed_min": 520.0,
        "speed_max": 1000.0,
        "vib_warning": 2.8,
        "vib_critical": 4.5,
        "pressure_nominal": 6.0,
        "pressure_max": 8.5,
        "energy_nominal": 11.0,
    },
    {
        "code": "PNT-01",
        "name": "Cabine de Pintura",
        "machine_type": MachineType.PAINT_BOOTH,
        "sequence": 4,
        "pos_x": 70.0,
        "pos_y": 60.0,
        "ideal_cycle_time_s": 12.0,
        "temp_nominal": 24.0,
        "temp_warning": 32.0,
        "temp_critical": 38.0,
        "speed_nominal": 18.0,
        "speed_min": 12.0,
        "speed_max": 25.0,
        "vib_warning": 2.0,
        "vib_critical": 3.5,
        "pressure_nominal": 4.2,
        "pressure_max": 6.0,
        "energy_nominal": 24.0,
    },
    {
        "code": "OVN-01",
        "name": "Forno de Cura",
        "machine_type": MachineType.OVEN,
        "sequence": 5,
        "pos_x": 70.0,
        "pos_y": 30.0,
        "ideal_cycle_time_s": 15.0,
        "temp_nominal": 165.0,
        "temp_warning": 185.0,
        "temp_critical": 200.0,
        "speed_nominal": 8.0,
        "speed_min": 5.0,
        "speed_max": 12.0,
        "vib_warning": 1.5,
        "vib_critical": 2.8,
        "pressure_nominal": 1.0,
        "pressure_max": 2.5,
        "energy_nominal": 82.0,
    },
    {
        "code": "INS-01",
        "name": "Estação de Inspeção Visual",
        "machine_type": MachineType.INSPECTION,
        "sequence": 6,
        "pos_x": 50.0,
        "pos_y": 30.0,
        "ideal_cycle_time_s": 3.0,
        "temp_nominal": 30.0,
        "temp_warning": 42.0,
        "temp_critical": 52.0,
        "speed_nominal": 120.0,
        "speed_min": 80.0,
        "speed_max": 160.0,
        "vib_warning": 1.2,
        "vib_critical": 2.2,
        "pressure_nominal": 0.0,
        "pressure_max": 1.0,
        "energy_nominal": 4.5,
        "eff_warning": 80.0,
        "eff_critical": 65.0,
    },
    {
        "code": "PKG-01",
        "name": "Empacotadora",
        "machine_type": MachineType.PACKAGER,
        "sequence": 7,
        "pos_x": 30.0,
        "pos_y": 30.0,
        "ideal_cycle_time_s": 4.5,
        "temp_nominal": 88.0,
        "temp_warning": 105.0,
        "temp_critical": 120.0,
        "speed_nominal": 60.0,
        "speed_min": 40.0,
        "speed_max": 85.0,
        "vib_warning": 3.2,
        "vib_critical": 5.0,
        "pressure_nominal": 5.5,
        "pressure_max": 7.5,
        "energy_nominal": 14.0,
    },
    {
        "code": "PAL-01",
        "name": "Paletizadora",
        "machine_type": MachineType.PALLETIZER,
        "sequence": 8,
        "pos_x": 10.0,
        "pos_y": 30.0,
        "ideal_cycle_time_s": 20.0,
        "temp_nominal": 42.0,
        "temp_warning": 58.0,
        "temp_critical": 70.0,
        "speed_nominal": 35.0,
        "speed_min": 22.0,
        "speed_max": 48.0,
        "vib_warning": 4.0,
        "vib_critical": 6.3,
        "pressure_nominal": 6.5,
        "pressure_max": 9.0,
        "energy_nominal": 19.0,
    },
]

#: Usuários de demonstração — um por perfil.
DEMO_USERS: list[dict] = [
    {
        "username": "operador",
        "email": "operador@factorytwin.io",
        "full_name": "Operador de Linha",
        "password": "operador123",
        "role": UserRole.OPERATOR,
    },
    {
        "username": "visitante",
        "email": "visitante@factorytwin.io",
        "full_name": "Visitante",
        "password": "visitante123",
        "role": UserRole.VIEWER,
    },
]


def seed_machines(db: Session) -> int:
    """Insere as máquinas ausentes. Idempotente — roda a cada boot."""
    existing = set(db.scalars(select(Machine.code)).all())
    created = 0
    for spec in MACHINE_CATALOG:
        if spec["code"] in existing:
            continue
        db.add(Machine(**spec, line="LINE-01", status=MachineStatus.IDLE))
        created += 1
    if created:
        db.commit()
        logger.info("Seed: %d máquinas criadas", created)
    return created


def seed_users(db: Session) -> int:
    """Cria o admin inicial e os usuários de demonstração, se não existirem."""
    existing = set(db.scalars(select(User.username)).all())
    created = 0

    if settings.FIRST_ADMIN_USERNAME not in existing:
        db.add(
            User(
                username=settings.FIRST_ADMIN_USERNAME,
                email=settings.FIRST_ADMIN_EMAIL,
                full_name="Administrador",
                hashed_password=hash_password(settings.FIRST_ADMIN_PASSWORD),
                role=UserRole.ADMIN,
            )
        )
        created += 1

    for spec in DEMO_USERS:
        if spec["username"] in existing:
            continue
        db.add(
            User(
                username=spec["username"],
                email=spec["email"],
                full_name=spec["full_name"],
                hashed_password=hash_password(spec["password"]),
                role=spec["role"],
            )
        )
        created += 1

    if created:
        db.commit()
        logger.info("Seed: %d usuários criados", created)
    return created


def seed_all(db: Session) -> None:
    seed_machines(db)
    seed_users(db)
