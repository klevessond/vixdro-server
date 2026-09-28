from rest_framework.routers import SimpleRouter

from .views import ProdutoViewSet

router = SimpleRouter()
router.register("produtos", ProdutoViewSet, basename="produto")

urlpatterns = router.urls
