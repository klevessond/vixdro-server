from django.urls import path
from rest_framework.routers import SimpleRouter

from .painel import PainelView
from .views import ProjetoViewSet

router = SimpleRouter()
router.register("projetos", ProjetoViewSet, basename="projeto")

urlpatterns = router.urls + [
    path("painel/", PainelView.as_view(), name="painel"),
]
