from django.urls import path

from .views import (
    EntradaProjetoView,
    ImagemPecaView,
    ItemView,
    ItensView,
    MinimoView,
    MovimentosView,
    PecaProntaView,
    PecasProntasView,
    ProduzirView,
    SimularProducaoView,
)

urlpatterns = [
    path("estoque/itens/", ItensView.as_view()),
    path("estoque/itens/<int:item_id>/", ItemView.as_view()),
    path("estoque/itens/<int:item_id>/minimo/", MinimoView.as_view()),
    path("estoque/movimentos/", MovimentosView.as_view()),
    path("estoque/entrada-projeto/", EntradaProjetoView.as_view()),
    path("estoque/pecas/", PecasProntasView.as_view()),
    path("estoque/pecas/simular/", SimularProducaoView.as_view()),
    path("estoque/pecas/produzir/", ProduzirView.as_view()),
    path("estoque/pecas/<uuid:peca_id>/", PecaProntaView.as_view()),
    path("estoque/pecas/<uuid:peca_id>/imagem/", ImagemPecaView.as_view()),
]
