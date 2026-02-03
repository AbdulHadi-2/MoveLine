from PIL import Image
from rest_framework import permissions, response, status, viewsets
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.views import APIView

from .models import OrderItem
from .serializers import OrderItemSerializer
from .fastvlm_service import (
    analyze_image,
    estimate_total_volume_m3,
    recommend_vehicle_type,
)


class OrderItemViewSet(viewsets.ModelViewSet):
    queryset = OrderItem.objects.select_related("order").all()
    serializer_class = OrderItemSerializer


class AnalyzeImageView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request):
        images = request.FILES.getlist("images")
        if not images:
            images = request.FILES.getlist("image")
        if not images:
            return response.Response(
                {"detail": "Image file is required (field: images or image)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        all_items = {}
        for image in images:
            try:
                pil_image = Image.open(image).convert("RGB")
            except Exception:
                return response.Response(
                    {"detail": "Invalid image file."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                result = analyze_image(pil_image)
            except Exception as exc:
                return response.Response(
                    {"detail": "Local inference failed.", "error": str(exc)},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            for item in result.get("items", []):
                label = item.get("label")
                if not label:
                    continue
                key = label
                if key not in all_items:
                    all_items[key] = {
                        "label": label,
                        "quantity": 0,
                        "is_fragile": False,
                    }
                all_items[key]["quantity"] += int(item.get("quantity", 1) or 1)
                all_items[key]["is_fragile"] = (
                    all_items[key]["is_fragile"] or bool(item.get("is_fragile"))
                )

        merged_items = sorted(all_items.values(), key=lambda x: x["label"])
        total_volume = estimate_total_volume_m3(merged_items)
        payload = {
            "items": merged_items,
            "estimated_total_volume_m3": round(total_volume, 2),
            "recommended_vehicle_type": recommend_vehicle_type(total_volume),
            "image_count": len(images),
        }
        return response.Response(payload, status=status.HTTP_200_OK)

    def patch(self, request):
        return self.post(request)
