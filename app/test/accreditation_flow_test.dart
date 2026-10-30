import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:app/features/home/home_screen.dart';
import 'package:app/services/api_client.dart';
import 'package:app/services/app_lock_service.dart';

void main() {
  setUp(() {
    FlutterSecureStorage.setMockInitialValues({});
    appLockService.isGuest = false;
    apiClient.currentUser = null;
    apiClient.mockRoleHandler = null;
    apiClient.mockAuthHandler = null;
  });

  testWidgets('Accreditation Flow - Collector can apply for accreditation and view status banner', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(() => tester.view.resetPhysicalSize());

    final mockApplications = <Map<String, dynamic>>[];

    apiClient.currentUser = {
      "id": "col_101",
      "email": "collector@arthentic.io",
      "roles": ["Collector"],
    };

    apiClient.mockRoleHandler = (endpoint, body) async {
      if (endpoint == "/v1/roles/my-applications") {
        return {"applications": mockApplications};
      } else if (endpoint == "/v1/roles/apply") {
        final newApp = {
          "id": "app_999",
          "requested_role": body["requested_role"],
          "status": "pending",
          "created_at": "2026-10-29T16:00:00Z",
          "review_note": null,
        };
        mockApplications.add(newApp);
        return {"success": true, "application": newApp};
      }
      return {};
    };

    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: HomeScreen(onTabSelected: (_) {}),
      ),
    ));
    await tester.pumpAndSettle();

    // Verify Collector sees "Apply for Accreditation"
    expect(find.text('Apply for Accreditation'), findsOneWidget);
    await tester.ensureVisible(find.text('Apply'));
    await tester.tap(find.text('Apply'));
    await tester.pumpAndSettle();

    // In modal: verify form fields exist
    expect(find.text('Submit Application'), findsOneWidget);
    expect(find.text('Attach proof of identity or diploma (PDF)'), findsOneWidget);

    // Toggle document attachment
    await tester.ensureVisible(find.text('Attach proof of identity or diploma (PDF)'));
    await tester.tap(find.text('Attach proof of identity or diploma (PDF)'));
    await tester.pumpAndSettle();
    expect(find.text('credentials_document.pdf attached'), findsOneWidget);

    // Submit application
    await tester.ensureVisible(find.text('Submit Application'));
    await tester.tap(find.text('Submit Application'));
    await tester.pumpAndSettle();

    // Verify modal dismissed and application appears in the status list
    expect(find.text('Artist Application'), findsOneWidget);
    expect(find.text('Pending Admin Review'), findsOneWidget);
  });

  testWidgets('Accreditation Flow - Admin can review pending application and approve', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(() => tester.view.resetPhysicalSize());

    final pendingApps = [
      {
        "id": "app_555",
        "user_id": "usr_44",
        "applicant_email": "applicant@arthentic.io",
        "requested_role": "Artist",
        "status": "pending",
        "created_at": "2026-10-29T12:00:00Z",
        "payload": {
          "bio_or_org": "Studio Verona",
          "notes": "Renowned oil painter",
          "portfolio_url": "https://verona.art",
        },
        "documents": [
          {"filename": "diploma.pdf"}
        ],
      }
    ];

    String? reviewedAppId;
    String? reviewedDecision;

    apiClient.currentUser = {
      "id": "admin_1",
      "email": "admin@arthentic.io",
      "roles": ["Admin"],
    };

    apiClient.mockRoleHandler = (endpoint, body) async {
      if (endpoint == "/v1/admin/applications") {
        return {"applications": pendingApps};
      } else if (endpoint.contains("/review")) {
        reviewedAppId = endpoint.split('/')[4];
        reviewedDecision = body["decision"];
        pendingApps.clear(); // reviewed and removed from pending
        return {"success": true};
      }
      return {};
    };

    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: HomeScreen(onTabSelected: (_) {}),
      ),
    ));
    await tester.pumpAndSettle();

    // Admin console review queue is displayed
    expect(find.text('Admin Accreditation Review'), findsOneWidget);
    expect(find.text('applicant@arthentic.io'), findsOneWidget);

    // Tap review item to open modal
    await tester.ensureVisible(find.text('applicant@arthentic.io'));
    await tester.tap(find.text('applicant@arthentic.io'));
    await tester.pumpAndSettle();

    expect(find.text('Review Application'), findsOneWidget);
    expect(find.text('Notes: Renowned oil painter'), findsOneWidget);
    expect(find.text('Approve'), findsOneWidget);
    expect(find.text('Reject'), findsOneWidget);

    // Tap Approve
    await tester.ensureVisible(find.text('Approve'));
    await tester.tap(find.text('Approve'));
    await tester.pumpAndSettle();

    expect(reviewedAppId, equals("app_555"));
    expect(reviewedDecision, equals("approve"));
    expect(find.text('Pending applications: 0'), findsOneWidget);
  });

  testWidgets('Accreditation Flow - Conservator can submit condition report', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(() => tester.view.resetPhysicalSize());

    final mockReports = <Map<String, dynamic>>[];
    Map<String, dynamic>? submittedReport;

    apiClient.currentUser = {
      "id": "conservator_1",
      "email": "conservator@arthentic.io",
      "roles": ["Conservator"],
    };

    apiClient.mockRoleHandler = (endpoint, body) async {
      if (endpoint == "/v1/conservation/reports") {
        if (body is Map && body.containsKey("tokenId")) {
          submittedReport = Map<String, dynamic>.from(body);
          mockReports.add({
            "id": "cr_1",
            "token_id": body["tokenId"],
            "condition_grade": body["condition_grade"],
            "notes": body["notes"],
            "treatment_performed": body["treatment_performed"],
            "created_at": "2026-10-29T16:05:00Z",
          });
          return {"success": true, "report": mockReports.last};
        } else {
          return {"reports": mockReports};
        }
      }
      return {};
    };

    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: HomeScreen(onTabSelected: (_) {}),
      ),
    ));
    await tester.pumpAndSettle();

    // Verify Conservator Lab Ready banner and "Add Report" button
    expect(find.text('Conservation Lab Ready'), findsOneWidget);
    expect(find.text('Add Report'), findsOneWidget);

    // Tap Add Report
    await tester.ensureVisible(find.text('Add Report'));
    await tester.tap(find.text('Add Report'));
    await tester.pumpAndSettle();

    expect(find.text('Record Condition Report'), findsOneWidget);
    expect(find.text('Record Report'), findsOneWidget);

    // Tap Record Report to submit
    await tester.ensureVisible(find.text('Record Report'));
    await tester.tap(find.text('Record Report'));
    await tester.pumpAndSettle();

    expect(submittedReport, isNotNull);
    expect(submittedReport!["condition_grade"], equals("Stable"));
  });
}
