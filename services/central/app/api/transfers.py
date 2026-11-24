from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from common.correlation import (
    get_correlation_id,
    generate_correlation_id
)

from app.domain.database import get_db
from app.domain.transfers import (
    create_transfer,
    IdempotencyConflict
)


router = APIRouter(tags=["Transfers"])


WarehouseId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=20
    )
]


class TransferCreate(BaseModel):
    source_warehouse_id: WarehouseId
    destination_warehouse_id: WarehouseId

    sku: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=100
        )
    ]

    quantity: int = Field(gt=0, le=2147483647, strict=True)


# --------------------------------------------------
# CREAR TRANSFERENCIA
# --------------------------------------------------

@router.post("/transfers", status_code=202)
def request_transfer(
    body: TransferCreate,
    idempotency_key: str = Header(
        alias="Idempotency-Key",
        min_length=1,
        max_length=255
    ),
    db: Session = Depends(get_db)
):
    if body.source_warehouse_id == body.destination_warehouse_id:
        raise HTTPException(
            status_code=422,
            detail="Origen y destino deben ser diferentes"
        )

    idempotency_key = idempotency_key.strip()

    if not idempotency_key:
        raise HTTPException(
            status_code=422,
            detail="Idempotency-Key no puede estar vacia"
        )

    correlation_id = (
        get_correlation_id()
        or generate_correlation_id()
    )

    try:
        transfer, created = create_transfer(
            db=db,
            idempotency_key=idempotency_key,
            source_warehouse_id=body.source_warehouse_id,
            destination_warehouse_id=body.destination_warehouse_id,
            sku=body.sku,
            quantity=body.quantity,
            correlation_id=correlation_id
        )

        db.commit()

    except IdempotencyConflict as exc:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail=str(exc)
        ) from exc

    except SQLAlchemyError as exc:
        db.rollback()

        raise HTTPException(
            status_code=503,
            detail="No se pudo registrar la transferencia"
        ) from exc

    return {
        "transfer_id": str(transfer["id"]),
        "status": (
            "PROCESSING" if created
            else transfer["status"]
        )
    }


# --------------------------------------------------
# CONSULTAR TRANSFERENCIA
# --------------------------------------------------

@router.get("/transfers/{transfer_id}")
def get_transfer(
    transfer_id: UUID,
    db: Session = Depends(get_db)
):
    try:
        transfer = db.execute(
            text("""
                SELECT *
                FROM transfers
                WHERE id = :id
            """),
            {"id": str(transfer_id)}
        ).mappings().first()

        if transfer is None:
            raise HTTPException(
                status_code=404,
                detail="Transferencia no encontrada"
            )

        history = db.execute(
            text("""
                SELECT
                    previous_status,
                    new_status,
                    reason,
                    correlation_id,
                    created_at
                FROM transfer_history
                WHERE transfer_id = :id
                ORDER BY id
            """),
            {"id": str(transfer_id)}
        ).mappings().all()

    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="No se pudo consultar la transferencia"
        ) from exc

    result = dict(transfer)

    result.pop("idempotency_key", None)

    result["transfer_id"] = str(result.pop("id"))
    result["history"] = [dict(row) for row in history]

    return result
