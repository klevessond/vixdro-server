from rest_framework.routers import SimpleRouter

from .views import CompromissoViewSet

router = SimpleRouter()
router.register("agenda", CompromissoViewSet, basename="compromisso")

urlpatterns = router.urls
