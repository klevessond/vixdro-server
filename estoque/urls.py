from django.urls import path

from .views import EntradaProjetoView, ItemView, ItensView, MinimoView, MovimentosView

urlpatterns = [
    path("estoque/itens/", ItensView.as_view()),
    path("estoque/itens/<int:item_id>/", ItemView.as_view()),
    path("estoque/itens/<int:item_id>/minimo/", MinimoView.as_view()),
    path("estoque/movimentos/", MovimentosView.as_view()),
    path("estoque/entrada-projeto/", EntradaProjetoView.as_view()),
]
