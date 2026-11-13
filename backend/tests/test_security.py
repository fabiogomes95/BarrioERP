"""Troca de passlib/python-jose por bcrypt/PyJWT: nada pode quebrar pra quem já tem senha/token."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import bcrypt
import jwt
import pytest

from app.core.config import settings
from app.core.security import create_access_token, decode_token, hash_password, verify_password

# Hash gerado pelo passlib (formato que está no banco hoje): "senha-antiga-123"
HASH_DO_PASSLIB = bcrypt.hashpw(b"senha-antiga-123", bcrypt.gensalt(rounds=4)).decode().replace("$2b$", "$2b$", 1)


def test_senha_cadastrada_antes_continua_valendo():
    assert verify_password("senha-antiga-123", HASH_DO_PASSLIB)
    assert not verify_password("senha-errada", HASH_DO_PASSLIB)


def test_hash_novo_tem_o_mesmo_formato():
    h = hash_password("SenhaForte123!")
    assert h.startswith("$2b$12$") and verify_password("SenhaForte123!", h)


def test_senha_longa_usa_so_72_bytes_sem_erro():
    longa = "x" * 100
    h = hash_password(longa)
    assert verify_password(longa, h) and verify_password("x" * 72 + "outra coisa", h)


@pytest.mark.parametrize("ruim", [None, "", "não-é-um-hash"])
def test_hash_vazio_ou_corrompido_e_senha_errada_nao_erro(ruim):
    assert verify_password("qualquer", ruim) is False


def test_token_emitido_pelo_python_jose_continua_valido():
    """Tokens de quem está logado na hora do reinício (HS256 padrão)."""
    agora = datetime.now(UTC)
    antigo = jwt.encode({"sub": str(uuid4()), "type": "access", "iat": agora, "exp": agora + timedelta(hours=1)},
                        settings.SECRET_KEY, algorithm="HS256")
    assert decode_token(antigo)["type"] == "access"


def test_token_vencido_ou_adulterado_e_recusado():
    vencido = jwt.encode({"sub": "x", "exp": datetime.now(UTC) - timedelta(minutes=1)}, settings.SECRET_KEY, algorithm="HS256")
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(vencido)
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(create_access_token(uuid4())[:-3] + "abc")
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(jwt.encode({"sub": "x"}, "outra-chave-qualquer-com-32-bytes-ok!!", algorithm="HS256"))
