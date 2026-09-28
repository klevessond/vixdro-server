import uuid

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models

UF_CHOICES = [
    (uf, uf)
    for uf in (
        "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR "
        "PE PI RJ RN RS RO RR SC SP SE TO"
    ).split()
]


class VidraceiroManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra):
        if not email:
            raise ValueError("O email é obrigatório.")
        email = self.normalize_email(email).strip().lower()
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("nome", "Administrador")
        return self.create_user(email, password, **extra)


class Vidraceiro(AbstractBaseUser, PermissionsMixin):
    # UUID como chave: o app gera o id offline, e reenvios da fila_sync
    # caem no mesmo registro em vez de duplicar.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    email = models.EmailField("email", unique=True)
    nome = models.CharField(max_length=150)
    empresa = models.CharField(max_length=150, blank=True)
    celular = models.CharField(max_length=20)
    cpf_cnpj = models.CharField("CPF/CNPJ", max_length=14, help_text="Somente dígitos")

    cep = models.CharField("CEP", max_length=8, blank=True, default="")
    rua = models.CharField(max_length=200)
    numero = models.CharField("número", max_length=20)
    complemento = models.CharField(max_length=100, blank=True)
    bairro = models.CharField(max_length=100)
    cidade = models.CharField(max_length=100)
    estado = models.CharField(max_length=2, choices=UF_CHOICES)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    objects = VidraceiroManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["nome"]

    class Meta:
        verbose_name = "vidraceiro"
        verbose_name_plural = "vidraceiros"

    def __str__(self):
        return f"{self.nome} <{self.email}>"
