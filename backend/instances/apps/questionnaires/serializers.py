from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from common.owned import OwnedPrimaryKeyRelatedField
from rest_framework import serializers

from . import refs
from .models import Battery, BatteryTypeRef, Questionnaire, QuestionnaireTypeRef


class OwnedRefField(OwnedPrimaryKeyRelatedField):
    """An owned type's copy. A copy that has not arrived yet is fetched once.

    `catalog` being unreachable is a 503, since the id may well be valid. Saying 400
    would tell the owner their type does not exist.
    """

    def to_internal_value(self, data):
        try:
            return super().to_internal_value(data)
        except serializers.ValidationError as exc:
            if "does_not_exist" not in exc.get_codes():
                raise
            model = self.get_queryset().model
            # Another owner's copy: nothing `catalog` says would change the answer.
            if model.objects.filter(pk=data).exists():
                raise
            ref = refs.read_through_or_503(model, data)
            if ref is None or ref.owner_id != self.context["request"].user.pk:
                raise
            return ref


class QuestionnaireTypeRefSerializer(serializers.ModelSerializer):
    """Same shape as `catalog`'s type response, embedded in each questionnaire."""

    questionnaireJson = serializers.JSONField(  # noqa: N815
        source="questionnaire_json", read_only=True
    )
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)  # noqa: N815
    updatedAt = serializers.DateTimeField(source="updated_at", read_only=True)  # noqa: N815

    class Meta:
        model = QuestionnaireTypeRef
        fields = ["id", "title", "questionnaireJson", "createdAt", "updatedAt"]
        read_only_fields = fields


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
    batteryTypeId = OwnedRefField(  # noqa: N815
        source="battery_type", queryset=BatteryTypeRef.objects.all()
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
    questionnaireTypeId = OwnedRefField(  # noqa: N815
        source="questionnaire_type", queryset=QuestionnaireTypeRef.objects.all()
    )
    questionnaireType = QuestionnaireTypeRefSerializer(  # noqa: N815
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
        self, value: QuestionnaireTypeRef
    ) -> QuestionnaireTypeRef:
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


class QuestionnaireListQuerySerializer(serializers.Serializer):
    """Filters on `GET /api/questionnaires/` (#10)."""

    questionnaireType = OwnedRefField(  # noqa: N815
        queryset=QuestionnaireTypeRef.objects.all(), required=False
    )
    submitted = serializers.BooleanField(required=False, allow_null=True, default=None)


class DashboardQuerySerializer(serializers.Serializer):
    days = serializers.ChoiceField(choices=[7, 30, 90], required=False)
    questionnaireType = OwnedRefField(  # noqa: N815
        queryset=QuestionnaireTypeRef.objects.all(), required=False
    )
    tz = serializers.CharField(required=False, max_length=64)

    def validate_tz(self, value: str) -> ZoneInfo:
        try:
            return ZoneInfo(value)
        # A directory such as "America", or a name that is not a valid path.
        except (ZoneInfoNotFoundError, ValueError, OSError) as exc:
            raise serializers.ValidationError("Unknown time zone.") from exc


class DashboardScoresQuerySerializer(DashboardQuerySerializer):
    questionnaireType = OwnedRefField(  # noqa: N815
        queryset=QuestionnaireTypeRef.objects.all()
    )
