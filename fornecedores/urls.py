from django.urls import path

from .views import CatalogoView, FornecedoresView

urlpatterns = [
    path("fornecedores/", FornecedoresView.as_view(), name="fornecedores"),
    path("catalogo/itens/", CatalogoView.as_view(), name="catalogo-itens"),
]
