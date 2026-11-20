"""
Usuários: quem pode criar/editar/remover quem, a proteção do último dono e
a troca de senha.

Em test_permissoes_rotas.py está quem acessa cada rota; aqui são as regras
dentro do serviço (um gerente não mexe em conta de dono, ninguém se apaga,
a empresa nunca fica sem dono).
"""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.core.exceptions import BusinessRuleError, ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.core.security import hash_password, verify_password
from app.models.user import User, UserRole as R
from app.schemas.user import ChangePasswordRequest, UserCreate, UserUpdate
from app.services.user_service import UserService

COMPANY = UUID("00000000-0000-0000-0000-000000000001")
EST = UUID("00000000-0000-0000-0000-000000000002")


def person(role: R, **kw) -> User:
    u = User(id=kw.pop("id", uuid4()), company_id=COMPANY, establishment_id=EST, name=f"{role.value}",
             email=f"{role.value}-{uuid4().hex[:6]}@bar.com", role=role, is_active=True,
             password_hash=kw.pop("password_hash", None), token_version=0)
    u.created_at = u.updated_at = datetime.now(UTC)
    u.deleted_at = None
    for k, v in kw.items():
        setattr(u, k, v)
    return u


class Banco:
    """Repositório simulado: usuários da empresa + quantos donos ativos existem."""

    def __init__(self, *users: User):
        self.users = {u.id: u for u in users}
        self.added: list[User] = []

    def repo(self) -> MagicMock:
        r = MagicMock()
        r.get_by_company = AsyncMock(side_effect=lambda uid, _c: self.users.get(uid))
        r.email_taken_in_company = AsyncMock(side_effect=lambda email, company_id, exclude_user_id=None: any(
            u.email == email.lower() and u.id != exclude_user_id for u in self.users.values()))
        r.count_active_owners = AsyncMock(side_effect=lambda _c: sum(
            1 for u in self.users.values() if u.role == R.OWNER and u.is_active and u.deleted_at is None))
        r.add = AsyncMock(side_effect=self._add)
        return r

    async def _add(self, u: User) -> User:
        u.id = uuid4()
        u.created_at = u.updated_at = datetime.now(UTC)
        u.token_version = 0
        self.users[u.id] = u
        self.added.append(u)
        return u


def as_(actor: User, banco: Banco) -> UserService:
    session = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    svc = UserService(session, actor)
    svc._repo = banco.repo()
    return svc


def novo(role: R, email="novo@bar.com") -> UserCreate:
    return UserCreate(name="Novo", email=email, password="1234", role=role)


# ── Criar ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("ator,alvo,pode", [
    (R.OWNER, R.OWNER, True), (R.OWNER, R.MANAGER, True), (R.OWNER, R.WAITER, True),
    (R.MANAGER, R.WAITER, True), (R.MANAGER, R.CASHIER, True), (R.MANAGER, R.MANAGER, True),
    (R.MANAGER, R.OWNER, False),                     # gerente não cria dono
    (R.CASHIER, R.WAITER, False), (R.WAITER, R.WAITER, False), (R.KITCHEN, R.WAITER, False),
])
async def test_quem_pode_criar_quem(ator, alvo, pode):
    me = person(ator)
    banco = Banco(me)
    svc = as_(me, banco)
    if pode:
        await svc.create(novo(alvo))
        assert banco.added[0].role == alvo
    else:
        with pytest.raises(ForbiddenError):
            await svc.create(novo(alvo))
        assert banco.added == []


async def test_usuario_novo_fica_no_mesmo_bar_com_senha_protegida_e_email_minusculo():
    dono = person(R.OWNER)
    banco = Banco(dono)
    await as_(dono, banco).create(novo(R.WAITER, email="Maria@Bar.com"))
    [u] = banco.added
    assert (u.company_id, u.establishment_id, u.email, u.is_active) == (COMPANY, EST, "maria@bar.com", True)
    assert u.password_hash != "1234" and verify_password("1234", u.password_hash)


async def test_email_repetido_e_recusado():
    dono = person(R.OWNER, email="maria@bar.com")
    banco = Banco(dono)
    with pytest.raises(ConflictError):
        await as_(dono, banco).create(novo(R.WAITER, email="MARIA@bar.com"))


# ── Editar ────────────────────────────────────────────────────────────────────

async def test_garcom_edita_o_proprio_nome_mas_nao_o_cargo_nem_os_outros():
    garcom, outro = person(R.WAITER), person(R.WAITER)
    svc = as_(garcom, Banco(garcom, outro))
    await svc.update(garcom.id, UserUpdate(name="Zé"))
    assert garcom.name == "Zé"
    with pytest.raises(ForbiddenError):
        await svc.update(garcom.id, UserUpdate(role=R.MANAGER))
    with pytest.raises(ForbiddenError):
        await svc.update(garcom.id, UserUpdate(is_active=False))
    with pytest.raises(ForbiddenError):
        await svc.update(outro.id, UserUpdate(name="x"))
    assert garcom.role == R.WAITER


async def test_gerente_nao_mexe_em_dono_nem_promove_a_dono():
    gerente, dono, garcom = person(R.MANAGER), person(R.OWNER), person(R.WAITER)
    svc = as_(gerente, Banco(gerente, dono, garcom))
    with pytest.raises(ForbiddenError):
        await svc.update(dono.id, UserUpdate(name="x"))
    with pytest.raises(ForbiddenError):
        await svc.update(garcom.id, UserUpdate(role=R.OWNER))
    with pytest.raises(ForbiddenError):
        await svc.update(gerente.id, UserUpdate(role=R.OWNER))      # nem a si mesmo
    assert garcom.role == R.WAITER and gerente.role == R.MANAGER


@pytest.mark.parametrize("mudanca", [UserUpdate(is_active=False), UserUpdate(role=R.MANAGER)])
async def test_unico_dono_nao_pode_ser_desativado_nem_rebaixado(mudanca):
    dono = person(R.OWNER)
    svc = as_(dono, Banco(dono))
    with pytest.raises(BusinessRuleError, match="último Owner"):
        await svc.update(dono.id, mudanca)
    assert dono.is_active and dono.role == R.OWNER


async def test_com_dois_donos_um_pode_ser_rebaixado():
    a, b = person(R.OWNER), person(R.OWNER)
    await as_(a, Banco(a, b)).update(b.id, UserUpdate(role=R.MANAGER))
    assert b.role == R.MANAGER


async def test_dono_inativo_nao_conta_como_segundo_dono():
    ativo, inativo = person(R.OWNER), person(R.OWNER, is_active=False)
    with pytest.raises(BusinessRuleError, match="último Owner"):
        await as_(ativo, Banco(ativo, inativo)).update(ativo.id, UserUpdate(is_active=False))


async def test_trocar_para_email_de_outro_e_recusado():
    dono, garcom = person(R.OWNER, email="dono@bar.com"), person(R.WAITER, email="ze@bar.com")
    svc = as_(dono, Banco(dono, garcom))
    with pytest.raises(ConflictError):
        await svc.update(garcom.id, UserUpdate(email="dono@bar.com"))
    await svc.update(garcom.id, UserUpdate(email="ZE@bar.com"))      # o próprio e-mail, outra caixa: ok
    assert garcom.email == "ze@bar.com"


async def test_usuario_de_outra_empresa_nao_aparece():
    dono = person(R.OWNER)
    svc = as_(dono, Banco(dono))
    with pytest.raises(NotFoundError):
        await svc.get(uuid4())
    with pytest.raises(NotFoundError):
        await svc.update(uuid4(), UserUpdate(name="x"))
    with pytest.raises(NotFoundError):
        await svc.delete(uuid4())


async def test_garcom_so_ve_o_proprio_perfil():
    garcom, outro = person(R.WAITER), person(R.WAITER)
    svc = as_(garcom, Banco(garcom, outro))
    assert (await svc.get(garcom.id)).id == garcom.id
    with pytest.raises(ForbiddenError):
        await svc.get(outro.id)


# ── Remover ───────────────────────────────────────────────────────────────────

async def test_ninguem_remove_a_propria_conta():
    a, b = person(R.OWNER), person(R.OWNER)
    with pytest.raises(BusinessRuleError, match="própria conta"):
        await as_(a, Banco(a, b)).delete(a.id)
    assert a.deleted_at is None


async def test_dono_remove_garcom():
    dono, garcom = person(R.OWNER), person(R.WAITER)
    await as_(dono, Banco(dono, garcom)).delete(garcom.id)
    assert garcom.deleted_at is not None


async def test_gerente_nao_remove_dono():
    gerente, dono = person(R.MANAGER), person(R.OWNER)
    with pytest.raises(ForbiddenError):
        await as_(gerente, Banco(gerente, dono)).delete(dono.id)
    assert dono.deleted_at is None


@pytest.mark.parametrize("ator", [R.CASHIER, R.WAITER, R.KITCHEN])
async def test_quem_nao_e_gerente_nao_remove_ninguem(ator):
    me, garcom = person(ator), person(R.WAITER)
    with pytest.raises(ForbiddenError):
        await as_(me, Banco(me, garcom)).delete(garcom.id)


# ── Senha ─────────────────────────────────────────────────────────────────────

def senha(nova="nova1", atual=None) -> ChangePasswordRequest:
    return ChangePasswordRequest(current_password=atual, new_password=nova, confirm_password=nova)


async def test_trocar_a_propria_senha_exige_a_atual():
    garcom = person(R.WAITER, password_hash=hash_password("velha"))
    svc = as_(garcom, Banco(garcom))
    with pytest.raises(ValidationError, match="senha atual"):
        await svc.change_password(garcom.id, senha())
    with pytest.raises(ValidationError, match="incorreta"):
        await svc.change_password(garcom.id, senha(atual="errada"))
    assert verify_password("velha", garcom.password_hash) and garcom.token_version == 0

    await svc.change_password(garcom.id, senha(atual="velha"))
    assert verify_password("nova1", garcom.password_hash)


async def test_trocar_senha_derruba_os_logins_abertos():
    """token_version sobe: quem estava logado com a senha antiga cai."""
    dono, garcom = person(R.OWNER), person(R.WAITER, password_hash=hash_password("x"))
    await as_(dono, Banco(dono, garcom)).change_password(garcom.id, senha())
    assert garcom.token_version == 1


async def test_gerente_reseta_senha_de_garcom_sem_saber_a_atual_mas_nao_a_do_dono():
    gerente, garcom, dono = person(R.MANAGER), person(R.WAITER), person(R.OWNER, password_hash=hash_password("d"))
    svc = as_(gerente, Banco(gerente, garcom, dono))
    await svc.change_password(garcom.id, senha())
    assert verify_password("nova1", garcom.password_hash)
    with pytest.raises(ForbiddenError):
        await svc.change_password(dono.id, senha())
    assert verify_password("d", dono.password_hash)


async def test_garcom_nao_troca_senha_de_outro():
    a, b = person(R.WAITER), person(R.WAITER, password_hash=hash_password("b"))
    with pytest.raises(ForbiddenError):
        await as_(a, Banco(a, b)).change_password(b.id, senha())


def test_senha_curta_ou_confirmacao_diferente_e_recusada():
    with pytest.raises(ValueError):
        ChangePasswordRequest(new_password="123", confirm_password="123")
    with pytest.raises(ValueError):
        ChangePasswordRequest(new_password="12345", confirm_password="54321")
