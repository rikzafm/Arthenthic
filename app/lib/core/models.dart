class ArtworkStatus {
  static const String CLEAR = "CLEAR";
  static const String CHIP_REPLACED = "CHIP_REPLACED";
  static const String UNSYNCHRONIZED_OWNERSHIP = "UNSYNCHRONIZED_OWNERSHIP";
  static const String FLAGGED = "FLAGGED";
  static const String DESTROYED = "DESTROYED";
}

class ArtworkInfo {
  final String tokenId;
  final String title;
  final String artist;
  final String lastVerified;

  const ArtworkInfo({
    required this.tokenId,
    required this.title,
    required this.artist,
    required this.lastVerified,
  });

  factory ArtworkInfo.mock() {
    return const ArtworkInfo(
      tokenId: "101",
      title: "Study in Blue and Gold",
      artist: "Elena Vance",
      lastVerified: "Oct 24, 2026",
    );
  }
}

class SunParams {
  final String uid;
  final int ctr;
  final String cmac;
  final String tamperStatus;

  SunParams({
    required this.uid,
    required this.ctr,
    required this.cmac,
    this.tamperStatus = 'TAMPER_OK',
  });

  bool get isTampered => tamperStatus.toUpperCase() == 'TAMPER_PERM_OPEN';

  Map<String, dynamic> toJson() => {
    'uid': uid,
    'ctr': ctr,
    'cmac': cmac,
    'tamperStatus': tamperStatus,
  };

  factory SunParams.fromJson(Map<String, dynamic> json) {
    return SunParams(
      uid: json['uid'] ?? '',
      ctr: json['ctr'] is int ? json['ctr'] : int.tryParse('${json['ctr']}') ?? 0,
      cmac: json['cmac'] ?? '',
      tamperStatus: json['tamperStatus'] ?? 'TAMPER_OK',
    );
  }
}

class Attestation {
  final String tokenId;
  final String sunDigest;
  final int similarityBps;
  final int deadline;
  final String nonce;
  final String signature;
  final String signer;

  Attestation({
    required this.tokenId,
    required this.sunDigest,
    required this.similarityBps,
    required this.deadline,
    required this.nonce,
    required this.signature,
    required this.signer,
  });

  factory Attestation.fromJson(Map<String, dynamic> json) {
    return Attestation(
      tokenId: '${json['tokenId']}',
      sunDigest: json['sunDigest'] ?? '',
      similarityBps: json['similarityBps'] is int ? json['similarityBps'] : int.tryParse('${json['similarityBps']}') ?? 0,
      deadline: json['deadline'] is int ? json['deadline'] : int.tryParse('${json['deadline']}') ?? 0,
      nonce: json['nonce'] ?? '',
      signature: json['signature'] ?? '',
      signer: json['signer'] ?? '',
    );
  }
}

class BranchScores {
  final int photoTexturePct;
  final int lidarReliefPct;
  final bool flatPrintPassed;

  BranchScores({
    required this.photoTexturePct,
    required this.lidarReliefPct,
    required this.flatPrintPassed,
  });

  factory BranchScores.fromJson(Map<String, dynamic> json) {
    return BranchScores(
      photoTexturePct: json['photoTexturePct'] ?? 94,
      lidarReliefPct: json['lidarReliefPct'] ?? 89,
      flatPrintPassed: json['flatPrintPassed'] ?? true,
    );
  }
}

class PointVerificationScore {
  final int pointIndex;
  final String name;
  final int similarityBps;
  final double similarityPct;
  final bool passed;
  final bool flatPrintPassed;
  final double reliefRoughnessMm;

  PointVerificationScore({
    required this.pointIndex,
    required this.name,
    required this.similarityBps,
    required this.similarityPct,
    required this.passed,
    required this.flatPrintPassed,
    required this.reliefRoughnessMm,
  });

  factory PointVerificationScore.fromJson(Map<String, dynamic> json) {
    return PointVerificationScore(
      pointIndex: json['pointIndex'] ?? 1,
      name: json['name'] ?? '',
      similarityBps: json['similarityBps'] ?? 0,
      similarityPct: (json['similarityPct'] is num) ? (json['similarityPct'] as num).toDouble() : 0.0,
      passed: json['passed'] ?? true,
      flatPrintPassed: json['flatPrintPassed'] ?? true,
      reliefRoughnessMm: (json['reliefRoughnessMm'] is num) ? (json['reliefRoughnessMm'] as num).toDouble() : 0.45,
    );
  }
}

class Level2Result {
  final bool isAuthentic;
  final int similarityBps;
  final int thresholdBps;
  final BranchScores branches;
  final Attestation attestation;
  final int? pointsPassed;
  final int? totalPoints;
  final int? requiredPoints;
  final List<PointVerificationScore>? pointBreakdown;

  Level2Result({
    required this.isAuthentic,
    required this.similarityBps,
    required this.thresholdBps,
    required this.branches,
    required this.attestation,
    this.pointsPassed,
    this.totalPoints,
    this.requiredPoints,
    this.pointBreakdown,
  });

  factory Level2Result.fromJson(Map<String, dynamic> json) {
    List<PointVerificationScore>? breakdown;
    if (json['pointBreakdown'] is List) {
      breakdown = (json['pointBreakdown'] as List)
          .map((item) => PointVerificationScore.fromJson(Map<String, dynamic>.from(item)))
          .toList();
    }

    return Level2Result(
      isAuthentic: json['isAuthentic'] ?? true,
      similarityBps: json['similarityBps'] ?? 9200,
      thresholdBps: json['thresholdBps'] ?? 8800,
      branches: BranchScores.fromJson(json['branches'] ?? {}),
      attestation: Attestation.fromJson(json['attestation'] ?? {}),
      pointsPassed: json['pointsPassed'],
      totalPoints: json['totalPoints'],
      requiredPoints: json['requiredPoints'],
      pointBreakdown: breakdown,
    );
  }
}

class ProvenanceEvent {
  final String type;
  final String timestamp;
  final String actor;
  final String role;
  final String details;

  ProvenanceEvent({
    required this.type,
    required this.timestamp,
    required this.actor,
    required this.role,
    required this.details,
  });

  factory ProvenanceEvent.fromJson(Map<String, dynamic> json) {
    return ProvenanceEvent(
      type: json['type'] ?? '',
      timestamp: json['timestamp'] ?? '',
      actor: json['actor'] ?? '',
      role: json['role'] ?? '',
      details: json['details'] ?? '',
    );
  }
}
