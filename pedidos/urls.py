from rest_framework.routers import SimpleRouter

from .views import PedidoViewSet

router = SimpleRouter()
router.register("pedidos", PedidoViewSet, basename="pedido")

urlpatterns = router.urls
