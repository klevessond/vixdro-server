from rest_framework.routers import SimpleRouter

from .views import ProjetoViewSet

router = SimpleRouter()
router.register("projetos", ProjetoViewSet, basename="projeto")

urlpatterns = router.urls
