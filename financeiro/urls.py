from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import CondicaoPagamentoViewSet, ContaViewSet, LancamentoViewSet, ResumoView

router = SimpleRouter()
router.register("financeiro/lancamentos", LancamentoViewSet, basename="lancamento")
router.register("financeiro/contas", ContaViewSet, basename="conta")
router.register("condicoes-pagamento", CondicaoPagamentoViewSet, basename="condicao-pagamento")

urlpatterns = router.urls + [
    path("financeiro/resumo/", ResumoView.as_view(), name="financeiro-resumo"),
]
