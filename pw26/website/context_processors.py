from .constants import GROUP_ALUNO, GROUP_PROFESSOR


def portal_user(request):
    user = request.user
    ctx = {
        "portal_student": None,
        "portal_professor": None,
        "is_student": False,
        "is_professor": False,
    }
    if not user.is_authenticated:
        return ctx

    if user.groups.filter(name=GROUP_ALUNO).exists():
        ctx["is_student"] = True
        ctx["portal_student"] = getattr(user, "student_profile", None)

    if user.groups.filter(name=GROUP_PROFESSOR).exists():
        ctx["is_professor"] = True
        ctx["portal_professor"] = getattr(user, "professor_profile", None)

    return ctx
