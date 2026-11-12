from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .cmapss_ml import artifact_status, predict_rul
from .ml_serializers import RULPredictionInputSerializer


class PredictiveMaintenanceAPIView(APIView):
    """Authenticated status/prediction endpoint for the CMAPSS RUL model."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(artifact_status())

    def post(self, request):
        serializer = RULPredictionInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = predict_rul(
                serializer.validated_data['history'],
                serializer.validated_data['cycle'],
            )
        except FileNotFoundError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except (ValueError, RuntimeError) as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result, status=status.HTTP_200_OK)
