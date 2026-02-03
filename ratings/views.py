from rest_framework import viewsets

from .models import Rating
from .serializers import RatingSerializer


class RatingViewSet(viewsets.ModelViewSet):
    queryset = Rating.objects.select_related("order", "customer", "driver")
    serializer_class = RatingSerializer
