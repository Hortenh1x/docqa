from app.core.security import (
    KEY_ENV_PREFIX,
    PREFIX_LENGTH,
    SECRET_LENGTH,
    generate_api_key,
    hash_api_key,
    split_api_key,
    verify_api_key,
)


def test_generate_roundtrip():
    plaintext, prefix, key_hash = generate_api_key()
    assert plaintext.startswith(KEY_ENV_PREFIX)
    assert len(plaintext) == len(KEY_ENV_PREFIX) + SECRET_LENGTH
    assert len(prefix) == PREFIX_LENGTH
    assert plaintext[len(KEY_ENV_PREFIX) :].startswith(prefix)
    assert split_api_key(plaintext) == prefix
    assert verify_api_key(plaintext, key_hash)


def test_keys_are_unique():
    keys = {generate_api_key()[0] for _ in range(50)}
    assert len(keys) == 50


def test_split_rejects_malformed():
    assert split_api_key("") is None
    assert split_api_key("garbage") is None
    assert split_api_key("dqa_live_short") is None
    assert split_api_key("dqa_live_" + "!" * 32) is None  # non-base62
    assert split_api_key("dqa_test_" + "a" * 32) is None  # wrong env prefix
    assert split_api_key("dqa_live_" + "a" * 33) is None  # wrong length


def test_verify_rejects_tampered_key():
    plaintext, _, key_hash = generate_api_key()
    tampered = plaintext[:-1] + ("A" if plaintext[-1] != "A" else "B")
    assert not verify_api_key(tampered, key_hash)
    assert not verify_api_key(plaintext, hash_api_key("other"))
