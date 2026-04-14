from .models import Professor, Student


def portal_user(request):
    ctx = {"portal_student": None, "portal_professor": None}
    sid = request.session.get("student_id")
    pid = request.session.get("professor_id")
    if sid:
        try:
            ctx["portal_student"] = Student.objects.get(pk=sid)
        except Student.DoesNotExist:
            request.session.pop("student_id", None)
    if pid:
        try:
            ctx["portal_professor"] = Professor.objects.get(pk=pid)
        except Professor.DoesNotExist:
            request.session.pop("professor_id", None)
    return ctx
