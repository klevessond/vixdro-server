from django.core.management.base import BaseCommand, CommandError

from fornecedores.models import Fornecedor, Sincronizacao
from fornecedores.sincronizacao import sincronizar


class Command(BaseCommand):
    help = "Sincroniza o catálogo de itens dos fornecedores ativos."

    def add_arguments(self, parser):
        parser.add_argument("--completa", action="store_true",
                            help="Baixa o catálogo inteiro e desativa o que sumiu (use semanalmente).")
        parser.add_argument("--fornecedor", help="slug de um fornecedor específico")

    def handle(self, *args, **opcoes):
        # Itens próprios dos vidraceiros não têm de onde sincronizar.
        fornecedores = Fornecedor.objects.filter(ativo=True, vidraceiro__isnull=True)
        if opcoes["fornecedor"]:
            fornecedores = fornecedores.filter(slug=opcoes["fornecedor"])
            if not fornecedores.exists():
                raise CommandError(f"Fornecedor ativo '{opcoes['fornecedor']}' não encontrado.")

        houve_erro = False
        for f in fornecedores:
            r = sincronizar(f, completa=opcoes["completa"])
            resumo = (f"{f.slug} [{r.tipo}] recebidos={r.recebidos} novos={r.novos} "
                      f"alterados={r.alterados} desativados={r.desativados} ignorados={r.ignorados}")
            if r.status == Sincronizacao.Status.SUCESSO:
                self.stdout.write(self.style.SUCCESS(f"OK   {resumo}"))
            else:
                houve_erro = True
                self.stdout.write(self.style.ERROR(f"ERRO {f.slug}: {r.erro}"))

        if houve_erro:
            raise CommandError("Uma ou mais sincronizações falharam (detalhes acima e no admin).")
