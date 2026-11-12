from rest_framework import serializers

from .cmapss_ml import INPUT_FEATURES


class RULPredictionInputSerializer(serializers.Serializer):
    cycle = serializers.IntegerField(min_value=1)
    history = serializers.ListField(
        child=serializers.ListField(child=serializers.FloatField()),
        min_length=1,
        max_length=500,
    )

    def validate_history(self, history):
        for index, row in enumerate(history, start=1):
            if len(row) != INPUT_FEATURES:
                raise serializers.ValidationError(
                    f'Ligne {index}: 24 valeurs attendues (3 réglages + 21 capteurs), {len(row)} reçues.'
                )
            if any(not (-1e12 < value < 1e12) for value in row):
                raise serializers.ValidationError(f'Ligne {index}: valeur numérique invalide.')
        return history

