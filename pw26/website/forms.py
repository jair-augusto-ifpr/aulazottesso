from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, UserCreationForm
from django.contrib.auth.models import User

from .models import ChatBot, Course, Material, Professor, ProfessorConfig, Student


INPUT_CLASS = {"class": "form-control"}
SELECT_CLASS = {"class": "form-select"}
CHECK_CLASS = {"class": "form-check-input"}


class StudentLoginForm(AuthenticationForm):
  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.fields["username"].label = "RA"
    self.fields["username"].widget.attrs.update(
      {
        "class": "form-control",
        "placeholder": "Seu registro acadêmico",
        "autocomplete": "username",
      }
    )
    self.fields["password"].widget.attrs.update(
      {
        "class": "form-control",
        "placeholder": "••••••••",
        "autocomplete": "current-password",
      }
    )


class ProfessorLoginForm(AuthenticationForm):
  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.fields["username"].label = "SIAPE"
    self.fields["username"].widget.attrs.update(
      {
        "class": "form-control",
        "placeholder": "Número SIAPE",
        "autocomplete": "username",
      }
    )
    self.fields["password"].widget.attrs.update(
      {
        "class": "form-control",
        "placeholder": "••••••••",
        "autocomplete": "current-password",
      }
    )


class PortalPasswordChangeForm(PasswordChangeForm):
  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    for field in self.fields.values():
      field.widget.attrs.update({"class": "form-control"})


class StudentSignupForm(forms.ModelForm):
  email = forms.EmailField(
    label="E-mail",
    widget=forms.EmailInput(attrs={**INPUT_CLASS, "autocomplete": "email"}),
  )
  password = forms.CharField(
    label="Senha",
    widget=forms.PasswordInput(
      attrs={**INPUT_CLASS, "autocomplete": "new-password"}
    ),
  )
  password_confirm = forms.CharField(
    label="Confirmar senha",
    widget=forms.PasswordInput(
      attrs={**INPUT_CLASS, "autocomplete": "new-password"}
    ),
  )
  phone = forms.CharField(
    label="Telefone",
    required=False,
    widget=forms.TextInput(
      attrs={
        **INPUT_CLASS,
        "id": "id_phone",
        "placeholder": "(44) 99999-9999",
        "data-mask": "phone",
      }
    ),
  )
  courses = forms.ModelMultipleChoiceField(
    label="Cursos",
    queryset=Course.objects.all(),
    required=False,
    widget=forms.CheckboxSelectMultiple(attrs=CHECK_CLASS),
  )

  class Meta:
    model = Student
    fields = ["name", "ra", "phone", "courses"]
    widgets = {
      "name": forms.TextInput(attrs=INPUT_CLASS),
      "ra": forms.TextInput(
        attrs={**INPUT_CLASS, "id": "id_ra", "data-mask": "ra"}
      ),
    }

  def clean_ra(self):
    ra = (self.cleaned_data.get("ra") or "").strip()
    if Student.objects.filter(ra=ra).exists():
      raise forms.ValidationError("Este RA já está cadastrado.")
    if User.objects.filter(username=ra).exists():
      raise forms.ValidationError("Este RA já está cadastrado.")
    return ra

  def clean_email(self):
    email = (self.cleaned_data.get("email") or "").strip()
    if User.objects.filter(email__iexact=email).exists():
      raise forms.ValidationError("Este e-mail já está cadastrado.")
    return email

  def clean(self):
    cleaned = super().clean()
    password = cleaned.get("password") or ""
    password_confirm = cleaned.get("password_confirm") or ""
    if password and password_confirm and password != password_confirm:
      self.add_error("password_confirm", "As senhas não conferem.")
    return cleaned


class ProfessorSignupForm(forms.ModelForm):
  email = forms.EmailField(
    label="E-mail",
    widget=forms.EmailInput(attrs={**INPUT_CLASS, "autocomplete": "email"}),
  )
  password = forms.CharField(
    label="Senha",
    widget=forms.PasswordInput(
      attrs={**INPUT_CLASS, "autocomplete": "new-password"}
    ),
  )
  password_confirm = forms.CharField(
    label="Confirmar senha",
    widget=forms.PasswordInput(
      attrs={**INPUT_CLASS, "autocomplete": "new-password"}
    ),
  )
  courses = forms.ModelMultipleChoiceField(
    label="Cursos",
    queryset=Course.objects.all(),
    required=False,
    widget=forms.CheckboxSelectMultiple(attrs=CHECK_CLASS),
  )

  class Meta:
    model = Professor
    fields = ["name", "siape", "courses"]
    widgets = {
      "name": forms.TextInput(attrs=INPUT_CLASS),
      "siape": forms.TextInput(attrs=INPUT_CLASS),
    }

  def clean_siape(self):
    siape = (self.cleaned_data.get("siape") or "").strip()
    if Professor.objects.filter(siape=siape).exists():
      raise forms.ValidationError("Este SIAPE já está cadastrado.")
    if User.objects.filter(username=siape).exists():
      raise forms.ValidationError("Este SIAPE já está cadastrado.")
    return siape

  def clean_email(self):
    email = (self.cleaned_data.get("email") or "").strip()
    if User.objects.filter(email__iexact=email).exists():
      raise forms.ValidationError("Este e-mail já está cadastrado.")
    return email

  def clean(self):
    cleaned = super().clean()
    password = cleaned.get("password") or ""
    password_confirm = cleaned.get("password_confirm") or ""
    if password and password_confirm and password != password_confirm:
      self.add_error("password_confirm", "As senhas não conferem.")
    return cleaned


class ChatMessageForm(forms.Form):
  message = forms.CharField(
    label="Sua pergunta",
    widget=forms.Textarea(
      attrs={
        "class": "form-control",
        "rows": 4,
        "placeholder": "Ex.: Quando começam as férias? Onde vejo o calendário?",
      }
    ),
  )


class CourseForm(forms.ModelForm):
  class Meta:
    model = Course
    fields = ["name"]
    widgets = {
      "name": forms.TextInput(
        attrs={**INPUT_CLASS, "placeholder": "Ex.: Informática"}
      ),
    }


class MaterialForm(forms.ModelForm):
  class Meta:
    model = Material
    fields = ["title", "text_content", "file", "public", "courses"]
    widgets = {
      "title": forms.TextInput(
        attrs={
          **INPUT_CLASS,
          "placeholder": "Ex.: Calendário acadêmico 2026",
        }
      ),
      "text_content": forms.Textarea(
        attrs={
          **INPUT_CLASS,
          "rows": 8,
          "placeholder": "Cole trechos ou resumo do documento para busca…",
        }
      ),
      "file": forms.ClearableFileInput(attrs=INPUT_CLASS),
      "courses": forms.CheckboxSelectMultiple(attrs=CHECK_CLASS),
      "public": forms.CheckboxInput(attrs=CHECK_CLASS),
    }

  def __init__(self, *args, professor=None, **kwargs):
    super().__init__(*args, **kwargs)
    if professor is not None:
      self.fields["courses"].queryset = professor.courses.all()
      if not professor.courses.exists():
        self.fields["courses"].help_text = (
          "Associe cursos ao professor no painel ou no admin."
        )


class ChatBotForm(forms.ModelForm):
  class Meta:
    model = ChatBot
    fields = ["prompt", "courses", "materials"]
    widgets = {
      "prompt": forms.Textarea(
        attrs={
          **INPUT_CLASS,
          "rows": 8,
          "placeholder": "Instruções para o assistente responder aos estudantes.",
        }
      ),
      "courses": forms.CheckboxSelectMultiple(attrs=CHECK_CLASS),
      "materials": forms.CheckboxSelectMultiple(attrs=CHECK_CLASS),
    }

  def __init__(self, *args, professor=None, **kwargs):
    super().__init__(*args, **kwargs)
    if professor is None:
      self.fields["courses"].queryset = Course.objects.none()
      self.fields["materials"].queryset = Material.objects.none()
      return

    professor_courses = professor.courses.all()
    self.fields["courses"].queryset = professor_courses
    self.fields["materials"].queryset = Material.objects.filter(
      owner=professor,
      courses__in=professor_courses,
    ).distinct()


class ProfessorConfigForm(forms.ModelForm):
  class Meta:
    model = ProfessorConfig
    fields = [
      "provider",
      "api_key",
      "model",
      "token_limit_per_student",
      "limit_period_days",
    ]
    widgets = {
      "provider": forms.Select(attrs=SELECT_CLASS),
      "api_key": forms.PasswordInput(
        render_value=True,
        attrs={**INPUT_CLASS, "placeholder": "Cole a chave da sua API"},
      ),
      "model": forms.TextInput(
        attrs={
          **INPUT_CLASS,
          "placeholder": "Ex.: gemini-2.5-flash ou openrouter/…",
        }
      ),
      "token_limit_per_student": forms.NumberInput(
        attrs={**INPUT_CLASS, "min": 0}
      ),
      "limit_period_days": forms.NumberInput(attrs={**INPUT_CLASS, "min": 0}),
    }

  def clean(self):
    cleaned = super().clean()
    provider = cleaned.get("provider")
    api_key = (cleaned.get("api_key") or "").strip()
    model = (cleaned.get("model") or "").strip()
    if provider or api_key or model:
      if not provider:
        self.add_error("provider", "Selecione o provedor.")
      if not api_key:
        self.add_error("api_key", "Informe a chave da API.")
      if not model:
        self.add_error("model", "Informe o modelo.")
    return cleaned
