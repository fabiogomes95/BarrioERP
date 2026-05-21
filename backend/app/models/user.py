import enum
from uuid import UUID

from sqlalchemy import Enum, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin


class UserRole(str, enum.Enum):
    OWNER = "owner"
    MANAGER = "manager"
    CASHIER = "cashier"
    WAITER = "waiter"
    KITCHEN = "kitchen"


class User(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    """Usuário do sistema — vinculado a uma Company e opcionalmente a um Establishment."""

    __tablename__ = "users"

    company_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    establishment_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("establishments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    pin_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role_enum"),
        nullable=False,
        default=UserRole.WAITER,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False, index=True)

    company: Mapped["Company"] = relationship(back_populates="users")  # noqa: F821
    establishment: Mapped["Establishment | None"] = relationship(back_populates="users")  # noqa: F821
    orders: Mapped[list["Order"]] = relationship(  # noqa: F821
        back_populates="waiter", foreign_keys="Order.waiter_id"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(  # noqa: F821
        back_populates="user"
    )

    __table_args__ = (
        Index("ix_users_company_email", "company_id", "email", unique=True),
        Index("ix_users_establishment_role", "establishment_id", "role"),
        Index("ix_users_company_active", "company_id", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email} role={self.role}>"
