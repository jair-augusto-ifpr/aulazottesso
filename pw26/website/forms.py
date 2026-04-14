from django import forms

from .models import ChatBot, Material


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
