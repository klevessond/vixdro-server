from django.urls import path

from rest_framework.routers import SimpleRouter

from .views import CatalogoView, FornecedoresView, MeusItensViewSet

router = SimpleRouter()
router.register("meus-itens", MeusItensViewSet, basename="meus-itens")

urlpatterns = [
    path("fornecedores/", FornecedoresView.as_view(), name="fornecedores"),
    path("catalogo/itens/", CatalogoView.as_view(), name="catalogo-itens"),
]

urlpatterns += router.urls
