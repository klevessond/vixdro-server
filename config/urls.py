from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("contas.urls")),
    path("api/v1/", include("fornecedores.urls")),
    path("api/v1/", include("produtos.urls")),
    path("api/v1/", include("clientes.urls")),
    path("api/v1/", include("projetos.urls")),
    path("api/v1/", include("pedidos.urls")),
]
