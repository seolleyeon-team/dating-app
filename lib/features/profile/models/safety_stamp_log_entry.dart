class SafetyStampLogEntry {
  const SafetyStampLogEntry({
    required this.logId,
    required this.promiseId,
    required this.roomId,
    required this.partnerId,
    required this.partnerName,
    required this.phase,
    required this.placeName,
    required this.stampedAt,
    this.latitude,
    this.longitude,
  });

  final String logId;
  final String promiseId;
  final String roomId;
  final String partnerId;
  final String partnerName;
  final String phase;
  final String placeName;
  final DateTime stampedAt;
  final double? latitude;
  final double? longitude;

  bool get isGoodbyeStamp => phase == 'goodbye';

  String get phaseLabel => isGoodbyeStamp ? '헤어짐 도장' : '만남 도장';

  SafetyStampLogEntry copyWith({
    String? logId,
    String? promiseId,
    String? roomId,
    String? partnerId,
    String? partnerName,
    String? phase,
    String? placeName,
    DateTime? stampedAt,
    double? latitude,
    double? longitude,
  }) {
    return SafetyStampLogEntry(
      logId: logId ?? this.logId,
      promiseId: promiseId ?? this.promiseId,
      roomId: roomId ?? this.roomId,
      partnerId: partnerId ?? this.partnerId,
      partnerName: partnerName ?? this.partnerName,
      phase: phase ?? this.phase,
      placeName: placeName ?? this.placeName,
      stampedAt: stampedAt ?? this.stampedAt,
      latitude: latitude ?? this.latitude,
      longitude: longitude ?? this.longitude,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'logId': logId,
      'promiseId': promiseId,
      'roomId': roomId,
      'partnerId': partnerId,
      'partnerName': partnerName,
      'phase': phase,
      'placeName': placeName,
      'stampedAt': stampedAt.toIso8601String(),
      'latitude': latitude,
      'longitude': longitude,
    };
  }

  factory SafetyStampLogEntry.fromJson(Map<String, dynamic> json) {
    return SafetyStampLogEntry(
      logId: json['logId']?.toString() ?? '',
      promiseId: json['promiseId']?.toString() ?? '',
      roomId: json['roomId']?.toString() ?? '',
      partnerId: json['partnerId']?.toString() ?? '',
      partnerName: json['partnerName']?.toString() ?? '상대방',
      phase: json['phase']?.toString() ?? 'meetup',
      placeName: json['placeName']?.toString() ?? '위치 정보 없음',
      stampedAt:
          DateTime.tryParse(json['stampedAt']?.toString() ?? '')?.toLocal() ??
          DateTime.fromMillisecondsSinceEpoch(0),
      latitude: _readDouble(json['latitude']),
      longitude: _readDouble(json['longitude']),
    );
  }

  static double? _readDouble(dynamic value) {
    if (value is num) return value.toDouble();
    return double.tryParse(value?.toString() ?? '');
  }
}
