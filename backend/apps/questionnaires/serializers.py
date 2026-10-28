from rest_framework import serializers

from .models import Battery, BatteryType, Questionnaire, QuestionnaireType


class OwnedPrimaryKeyRelatedField(serializers.PrimaryKeyRelatedField):
    """Accept only primary keys of objects owned by the requesting user."""

    def get_queryset(self):
        return super().get_queryset().filter(owner=self.context["request"].user)


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


class BatterySlotSerializer(serializers.ModelSerializer):
    order = serializers.IntegerField(source="battery_order", read_only=True)
    questionnaireId = serializers.UUIDField(source="id", read_only=True)  # noqa: N815
    shareToken = serializers.UUIDField(source="share_token", read_only=True)  # noqa: N815
    questionnaireTypeName = serializers.CharField(  # noqa: N815
        source="questionnaire_type.title", read_only=True
    )
    submittedAt = serializers.DateTimeField(source="submitted_at", read_only=True)  # noqa: N815

    class Meta:
        model = Questionnaire
        fields = [
            "order",
            "questionnaireId",
            "shareToken",
            "questionnaireTypeName",
            "submittedAt",
        ]


class BatterySerializer(serializers.ModelSerializer):
    batteryTypeId = OwnedPrimaryKeyRelatedField(  # noqa: N815
        source="battery_type", queryset=BatteryType.objects.all()
    )
    batteryTypeName = serializers.CharField(  # noqa: N815
        source="battery_type.title", read_only=True
    )
    shareToken = serializers.UUIDField(source="share_token", read_only=True)  # noqa: N815
    questionnaires = BatterySlotSerializer(many=True, read_only=True)
    isComplete = serializers.SerializerMethodField()  # noqa: N815
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)  # noqa: N815
    updatedAt = serializers.DateTimeField(source="updated_at", read_only=True)  # noqa: N815

    class Meta:
        model = Battery
        fields = [
            "id",
            "batteryTypeId",
            "batteryTypeName",
            "name",
            "shareToken",
            "questionnaires",
            "isComplete",
            "createdAt",
            "updatedAt",
        ]
        read_only_fields = ["id"]

    def get_isComplete(self, obj: Battery) -> bool:  # noqa: N802
        slots = obj.questionnaires.all()
        return bool(slots) and all(q.submitted_at is not None for q in slots)


class QuestionnaireSerializer(serializers.ModelSerializer):
    questionnaireTypeId = OwnedPrimaryKeyRelatedField(  # noqa: N815
        source="questionnaire_type", queryset=QuestionnaireType.objects.all()
    )
    questionnaireType = QuestionnaireTypeSerializer(  # noqa: N815
        source="questionnaire_type", read_only=True
    )
    batteryId = serializers.UUIDField(source="battery_id", read_only=True)  # noqa: N815
    batteryOrder = serializers.IntegerField(source="battery_order", read_only=True)  # noqa: N815
    shareToken = serializers.UUIDField(source="share_token", read_only=True)  # noqa: N815
    answers = serializers.JSONField(source="answers_json", read_only=True)
    metrics = serializers.JSONField(source="metrics_json", read_only=True)
    submittedAt = serializers.DateTimeField(source="submitted_at", read_only=True)  # noqa: N815
    questionnaireJsonSnapshot = serializers.JSONField(  # noqa: N815
        source="questionnaire_json_snapshot", read_only=True
    )
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)  # noqa: N815
    updatedAt = serializers.DateTimeField(source="updated_at", read_only=True)  # noqa: N815

    class Meta:
        model = Questionnaire
        fields = [
            "id",
            "questionnaireTypeId",
            "questionnaireType",
            "batteryId",
            "batteryOrder",
            "name",
            "shareToken",
            "answers",
            "metrics",
            "submittedAt",
            "questionnaireJsonSnapshot",
            "createdAt",
            "updatedAt",
        ]
        read_only_fields = ["id"]

    def validate_questionnaireTypeId(  # noqa: N802
        self, value: QuestionnaireType
    ) -> QuestionnaireType:
        if (
            self.instance is not None
            and value.pk != self.instance.questionnaire_type_id
        ):
            raise serializers.ValidationError(
                "The type of an existing questionnaire cannot change."
            )
        return value


# ── Public (share-token) serializers: only what a respondent needs ────────────


class PublicQuestionnaireSerializer(serializers.ModelSerializer):
    questionnaireTypeTitle = serializers.CharField(  # noqa: N815
        source="questionnaire_type.title", read_only=True
    )
    questionnaireJson = serializers.SerializerMethodField()  # noqa: N815
    submittedAt = serializers.DateTimeField(source="submitted_at", read_only=True)  # noqa: N815

    class Meta:
        model = Questionnaire
        fields = [
            "id",
            "name",
            "questionnaireTypeTitle",
            "questionnaireJson",
            "submittedAt",
        ]
        read_only_fields = fields

    def get_questionnaireJson(self, obj: Questionnaire) -> dict:  # noqa: N802
        # A submitted questionnaire shows the definition it was answered against.
        if obj.submitted_at is not None:
            return obj.questionnaire_json_snapshot
        return obj.questionnaire_type.questionnaire_json


class PublicBatterySlotSerializer(BatterySlotSerializer):
    class Meta(BatterySlotSerializer.Meta):
        fields = ["order", "shareToken", "questionnaireTypeName", "submittedAt"]


class PublicBatterySerializer(serializers.ModelSerializer):
    batteryTypeName = serializers.CharField(  # noqa: N815
        source="battery_type.title", read_only=True
    )
    questionnaires = PublicBatterySlotSerializer(many=True, read_only=True)
    isComplete = serializers.SerializerMethodField()  # noqa: N815

    class Meta:
        model = Battery
        fields = ["id", "name", "batteryTypeName", "questionnaires", "isComplete"]
        read_only_fields = fields

    get_isComplete = BatterySerializer.get_isComplete  # noqa: N815


class SubmitSerializer(serializers.Serializer):
    answers = serializers.DictField()
    metrics = serializers.DictField(required=False, default=dict)
