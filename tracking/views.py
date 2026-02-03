from rest_framework import viewsets

from .models import Tracking
from .serializers import TrackingSerializer


class TrackingViewSet(viewsets.ModelViewSet):
    queryset = Tracking.objects.select_related("order", "driver").all()
    serializer_class = TrackingSerializer
