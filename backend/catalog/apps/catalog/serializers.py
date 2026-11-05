from common.owned import OwnedPrimaryKeyRelatedField
from rest_framework import serializers

from .models import BatteryType, QuestionnaireType


class QuestionnaireTypeSerializer(serializers.ModelSerializer):
    questionnaireJson = serializers.JSONField(  # noqa: N815
        source="questionnaire_json", required=False
    )
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)  # noqa: N815
    updatedAt = serializers.DateTimeField(source="updated_at", read_only=True)  # noqa: N815

    class Meta:
        model = QuestionnaireType
        fields = ["id", "title", "questionnaireJson", "createdAt", "updatedAt"]
        read_only_fields = ["id"]


class BatteryTypeSerializer(serializers.ModelSerializer):
    # Written as an ordered list of IDs; the view stores it via
    # services.set_battery_type_items. Read back from the prefetched items.
    questionnaireTypeIds = OwnedPrimaryKeyRelatedField(  # noqa: N815
        many=True, required=False, queryset=QuestionnaireType.objects.all()
    )
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)  # noqa: N815
    updatedAt = serializers.DateTimeField(source="updated_at", read_only=True)  # noqa: N815

    class Meta:
        model = BatteryType
        fields = [
            "id",
            "title",
            "description",
            "questionnaireTypeIds",
            "createdAt",
            "updatedAt",
        ]
        read_only_fields = ["id"]

    def to_representation(self, instance):
        data = {
            name: field.to_representation(getattr(instance, field.source))
            for name, field in self.fields.items()
            if name != "questionnaireTypeIds"
        }
        data["questionnaireTypeIds"] = [
            str(item.questionnaire_type_id) for item in instance.items.all()
        ]
        return data
