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

    group_names = set(user.groups.values_list("name", flat=True))
    if GROUP_ALUNO in group_names:
        ctx["is_student"] = True
        ctx["portal_student"] = getattr(user, "student_profile", None)

    if GROUP_PROFESSOR in group_names:
        ctx["is_professor"] = True
        ctx["portal_professor"] = getattr(user, "professor_profile", None)

    return ctx
