"""Certificate template management endpoints."""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from api.dependencies import PaginationParams, get_db, require_api_key
from core.exceptions import TemplateNotFoundError
from models import DEFAULT_LAYOUT_CONFIG, CertificateTemplate
from schemas.template import TemplateCreate, TemplateRead
from services.certificate_service import CertificateRenderer

router = APIRouter(prefix="/templates", tags=["Templates"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=TemplateRead,
    dependencies=[Depends(require_api_key)],
    summary="Create a new certificate template",
)
def create_template(
    payload: TemplateCreate,
    db: Session = Depends(get_db),
) -> TemplateRead:
    """Register a new certificate template with layout configuration."""
    layout = payload.layout_config or DEFAULT_LAYOUT_CONFIG

    # Validate layout configuration before persisting
    CertificateRenderer(layout_config=layout)

    # Determine latest version for this template name
    latest_version = (
        db.scalar(
            select(CertificateTemplate.version)
            .where(CertificateTemplate.name == payload.name)
            .order_by(desc(CertificateTemplate.version))
        )
        or 0
    )

    new_version = latest_version + 1

    template = CertificateTemplate(
        name=payload.name,
        version=new_version,
        is_active=True,
        title=payload.title,
        description_pattern=payload.description_pattern,
        issuer_name=payload.issuer_name,
        layout_config=layout,
    )
    db.add(template)
    db.commit()
    db.refresh(template)

    return TemplateRead.model_validate(template)


@router.get(
    "",
    response_model=list[TemplateRead],
    summary="List all certificate templates",
)
def list_templates(
    db: Session = Depends(get_db),
    pagination: PaginationParams = Depends(),
) -> list[TemplateRead]:
    """Retrieve all available certificate templates."""
    templates = (
        db.execute(
            select(CertificateTemplate)
            .order_by(desc(CertificateTemplate.created_at))
            .offset(pagination.skip)
            .limit(pagination.limit)
        )
        .scalars()
        .all()
    )

    return [TemplateRead.model_validate(t) for t in templates]


@router.get(
    "/{template_id}",
    response_model=TemplateRead,
    summary="Retrieve certificate template by UUID",
)
def get_template(
    template_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> TemplateRead:
    """Fetch specific certificate template details."""
    template = db.execute(
        select(CertificateTemplate).where(CertificateTemplate.id == template_id)
    ).scalar_one_or_none()

    if not template:
        raise TemplateNotFoundError(str(template_id))

    return TemplateRead.model_validate(template)


@router.put(
    "/{template_id}/activate",
    response_model=TemplateRead,
    dependencies=[Depends(require_api_key)],
    summary="Activate certificate template",
)
def activate_template(
    template_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> TemplateRead:
    """Mark a certificate template as active."""
    template = db.execute(
        select(CertificateTemplate).where(CertificateTemplate.id == template_id)
    ).scalar_one_or_none()

    if not template:
        raise TemplateNotFoundError(str(template_id))

    template.is_active = True
    db.commit()
    db.refresh(template)

    return TemplateRead.model_validate(template)
