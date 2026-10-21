from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import LancamentoViewSet, ResumoView

router = SimpleRouter()
router.register("financeiro/lancamentos", LancamentoViewSet, basename="lancamento")

urlpatterns = router.urls + [
    path("financeiro/resumo/", ResumoView.as_view(), name="financeiro-resumo"),
]
