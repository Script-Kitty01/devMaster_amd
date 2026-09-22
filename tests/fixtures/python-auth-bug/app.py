def authorize(user, required_role):
    return user.get("role") == required_role


def login(request):
    user = request.get("user")
    role = request.get("role")
    if authorize(user, role):
        return {"ok": True}
    return {"ok": False}
