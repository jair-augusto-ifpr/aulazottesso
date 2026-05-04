from django import forms

from .models import ChatBot, Course, Material, Professor, Student


class StudentLoginForm(forms.Form):
    ra = forms.CharField(
        label="RA",
        max_length=50,
        widget=forms.TextInput(
            attrs={
                "class": "input-control",
                "placeholder": "Seu registro acadêmico",
                "autocomplete": "username",
            }
        ),
    )
    password = forms.CharField(
        label="Senha",
        widget=forms.PasswordInput(
            attrs={
                "class": "input-control",
                "placeholder": "••••••••",
                "autocomplete": "current-password",
            }
        ),
    )


class ProfessorLoginForm(forms.Form):
    siape = forms.CharField(
        label="SIAPE",
        max_length=50,
        widget=forms.TextInput(
            attrs={
                "class": "input-control",
                "placeholder": "Número SIAPE",
                "autocomplete": "username",
            }
        ),
    )
    password = forms.CharField(
        label="Senha",
        widget=forms.PasswordInput(
            attrs={
                "class": "input-control",
                "placeholder": "••••••••",
                "autocomplete": "current-password",
            }
        ),
    )


class StudentSignupForm(forms.ModelForm):
    password = forms.CharField(
        label="Senha",
        widget=forms.PasswordInput(
            attrs={
                "class": "input-control",
                "placeholder": "••••••••",
                "autocomplete": "new-password",
            }
        ),
    )
    password_confirm = forms.CharField(
        label="Confirmar senha",
        widget=forms.PasswordInput(
            attrs={
                "class": "input-control",
                "placeholder": "Repita a senha",
                "autocomplete": "new-password",
            }
        ),
    )
    courses = forms.ModelMultipleChoiceField(
        label="Cursos",
        queryset=Course.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Student
        fields = ["name", "ra", "email", "courses", "password", "password_confirm"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "input-control"}),
            "ra": forms.TextInput(attrs={"class": "input-control"}),
            "email": forms.TextInput(attrs={"class": "input-control"}),
        }

    def clean_ra(self):
        ra = (self.cleaned_data.get("ra") or "").strip()
        if Student.objects.filter(ra=ra).exists():
            raise forms.ValidationError("Este RA já está cadastrado.")
        return ra

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip()
        if Student.objects.filter(email__iexact=email).exists():
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
    password = forms.CharField(
        label="Senha",
        widget=forms.PasswordInput(
            attrs={
                "class": "input-control",
                "placeholder": "••••••••",
                "autocomplete": "new-password",
            }
        ),
    )
    password_confirm = forms.CharField(
        label="Confirmar senha",
        widget=forms.PasswordInput(
            attrs={
                "class": "input-control",
                "placeholder": "Repita a senha",
                "autocomplete": "new-password",
            }
        ),
    )
    courses = forms.ModelMultipleChoiceField(
        label="Cursos",
        queryset=Course.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Professor
        fields = ["name", "siape", "email", "courses", "password", "password_confirm"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "input-control"}),
            "siape": forms.TextInput(attrs={"class": "input-control"}),
            "email": forms.TextInput(attrs={"class": "input-control"}),
        }

    def clean_siape(self):
        siape = (self.cleaned_data.get("siape") or "").strip()
        if Professor.objects.filter(siape=siape).exists():
            raise forms.ValidationError("Este SIAPE já está cadastrado.")
        return siape

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip()
        if Professor.objects.filter(email__iexact=email).exists():
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
                "class": "input-control",
                "rows": 4,
                "placeholder": "Ex.: Quando começam as férias? Onde vejo o calendário?",
            }
        ),
    )


class MaterialForm(forms.ModelForm):
    chatbots = forms.ModelMultipleChoiceField(
        label="Vincular aos chatbots",
        queryset=ChatBot.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Material
        fields = ["title", "text_content", "file", "public", "courses"]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "input-control",
                    "placeholder": "Ex.: Calendário acadêmico 2026",
                }
            ),
            "text_content": forms.Textarea(
                attrs={
                    "class": "input-control",
                    "rows": 8,
                    "placeholder": "Cole trechos ou resumo do documento para busca por palavras-chave…",
                }
            ),
            "file": forms.ClearableFileInput(
                attrs={"class": "input-control"}
            ),
            "courses": forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, professor=None, **kwargs):
        super().__init__(*args, **kwargs)
        if professor is not None:
            self.fields["courses"].queryset = professor.courses.all()
            self.fields["chatbots"].queryset = professor.chatbots.all()
            if not professor.courses.exists():
                self.fields["courses"].help_text = "Cadastre cursos para o professor no admin."
            if not professor.chatbots.exists():
                self.fields["chatbots"].help_text = "Crie um chatbot para este professor no admin."


class ChatBotForm(forms.ModelForm):
    class Meta:
        model = ChatBot
        fields = ["prompt", "courses", "materials"]
        widgets = {
            "prompt": forms.Textarea(
                attrs={
                    "class": "input-control",
                    "rows": 8,
                    "placeholder": "Defina instruções para o assistente responder aos estudantes.",
                }
            ),
            "courses": forms.CheckboxSelectMultiple,
            "materials": forms.CheckboxSelectMultiple,
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
            courses__in=professor_courses
        ).distinct()
