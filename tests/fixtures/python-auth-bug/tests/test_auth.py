from app import authorize


def test_authorize_requires_role():
    assert authorize({"role": "user"}, "admin") is False
    assert authorize({"role": "admin"}, "admin") is True
