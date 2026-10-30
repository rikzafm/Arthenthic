import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'core/theme.dart';
import 'core/platform_capabilities.dart';
import 'features/auth/app_lock_gate.dart';
import 'features/auth/splash_screen.dart';
import 'features/home/home_screen.dart';
import 'features/provenance/provenance_screen.dart';
import 'features/wallet/wallet_screen.dart';
import 'features/marketplace/marketplace_screen.dart';
import 'features/web_consoles/gallery_safe_console.dart';
import 'features/web_consoles/conservator_console.dart';
import 'features/web_consoles/admin_incident_console.dart';
import 'features/verify/public_nfc_tap_screen.dart';
import 'features/genesis/genesis_intake_screen.dart';
import 'features/genesis/coa_screen.dart';
import 'features/conservation/restoration_screen.dart';
import 'features/dashboards/artist_dashboard.dart';
import 'features/dashboards/collector_dashboard.dart';
import 'services/api_client.dart';
import 'services/wallet_service.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const ArthenticApp());
}

class ArthenticApp extends StatelessWidget {
  final Widget? home;
  final String? initialRoute;

  const ArthenticApp({super.key, this.home, this.initialRoute});

  static Widget? _resolveDeepLinkWidget(String? routeStr) {
    if (routeStr == null || routeStr.isEmpty) return null;
    final uri = Uri.tryParse(routeStr);
    if (uri == null) return null;
    final path = uri.path.toLowerCase();

    // 1. D-14* Zero-Install Public NFC Tap Web Viewer
    if (path.contains('/verify')) {
      final uid = uri.queryParameters['uid'] ?? '04A1B2C3D4E580';
      final ctr = int.tryParse(uri.queryParameters['ctr'] ?? '1') ?? 1;
      final cmac = uri.queryParameters['cmac'] ?? 'A9E38F107B5C2D44';
      return PublicNfcTapScreen(uid: uid, ctr: ctr, cmac: cmac);
    }

    // 2. B-12 Public Certificate of Authenticity (CoA)
    if (path.contains('/coa')) {
      final tokenId = uri.queryParameters['tokenId'] ??
          (uri.pathSegments.length > 1 ? uri.pathSegments[1] : '101');
      return CertificateOfAuthenticityScreen(tokenId: tokenId);
    }

    // 3. Institutional Web Consoles (Web Portals 1-3)
    if (path.contains('/console/gallery') || path.contains('/gallery')) {
      return const GallerySafeConsole();
    }
    if (path.contains('/console/conservator') || path.contains('/conservator')) {
      return const ConservatorStudioConsole();
    }
    if (path.contains('/console/admin') || path.contains('/governance')) {
      return const AdminIncidentConsole();
    }

    // 4. Genesis Intake Wizard (B-01..B-08)
    if (path.contains('/intake') || path.contains('/genesis')) {
      return const GenesisIntakeScreen();
    }

    // 5. Restoration & 3-of-3 Chip Governance (E-01..E-07*, F-05)
    if (path.contains('/restoration')) {
      final tokenId = uri.queryParameters['tokenId'] ?? '101';
      return RestorationScreen(tokenId: tokenId);
    }

    // 6. Dashboards
    if (path.contains('/dashboard/artist')) {
      return const ArtistDashboardScreen();
    }
    if (path.contains('/dashboard/collector')) {
      return const CollectorDashboardScreen();
    }

    final uid = uri.queryParameters['uid'];
    if (uid != null && uid.isNotEmpty) {
      final ctr = int.tryParse(uri.queryParameters['ctr'] ?? '1') ?? 1;
      final cmac = uri.queryParameters['cmac'] ?? 'A9E38F107B5C2D44';
      return PublicNfcTapScreen(uid: uid, ctr: ctr, cmac: cmac);
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final deepLinked = _resolveDeepLinkWidget(initialRoute) ??
        _resolveDeepLinkWidget(Uri.base.toString());
    return MaterialApp(
      title: 'Arthentic',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.lightTheme,
      home: home ?? deepLinked ?? const SplashScreen(),
    );
  }
}

class MainTabShell extends StatefulWidget {
  final int initialIndex;
  const MainTabShell({super.key, this.initialIndex = 0});

  @override
  State<MainTabShell> createState() => _MainTabShellState();
}

class _MainTabShellState extends State<MainTabShell> {
  late int _currentIndex;

  @override
  void initState() {
    super.initState();
    _currentIndex = widget.initialIndex;
    _initApp();
  }

  Future<void> _initApp() async {
    if (apiClient.accessToken == null) {
      final restored = await apiClient.restoreSession();
      if (!restored) {
        await apiClient.login(walletService.address);
      }
    }
  }

  void _onTabSelected(int index) {
    setState(() => _currentIndex = index);
  }

  @override
  Widget build(BuildContext context) {
    final screenWidth = MediaQuery.of(context).size.width;
    final isDesktop = PlatformCapabilities.isDesktopConsole(screenWidth);

    final standardScreens = [
      HomeScreen(onTabSelected: _onTabSelected),
      const ProvenanceScreen(),
      const WalletScreen(),
      const MarketplaceScreen(),
    ];

    final desktopScreens = [
      ...standardScreens,
      const GallerySafeConsole(),
      const ConservatorStudioConsole(),
      const AdminIncidentConsole(),
    ];

    if (isDesktop) {
      // Expanded Desktop / Web Institutional Console View (Part IV, Section 5.2)
      return AppLockGate(
        child: Scaffold(
          body: Row(
            children: [
              NavigationRail(
                selectedIndex: _currentIndex < desktopScreens.length ? _currentIndex : 0,
                onDestinationSelected: _onTabSelected,
                labelType: NavigationRailLabelType.all,
                backgroundColor: Colors.white,
                selectedIconTheme: const IconThemeData(color: AppTheme.brandBlue),
                unselectedIconTheme: const IconThemeData(color: Color(0xFF64748B)),
                selectedLabelTextStyle: GoogleFonts.inter(
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                  color: AppTheme.brandBlue,
                ),
                unselectedLabelTextStyle: GoogleFonts.inter(
                  fontSize: 11,
                  fontWeight: FontWeight.w500,
                  color: const Color(0xFF64748B),
                ),
                leading: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 20),
                  child: Column(
                    children: [
                      Container(
                        width: 40,
                        height: 40,
                        decoration: BoxDecoration(
                          color: AppTheme.brandDark,
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: const Icon(Icons.palette_rounded, color: Colors.white, size: 22),
                      ),
                      const SizedBox(height: 6),
                      Text("ARTHENTIC", style: GoogleFonts.inter(fontSize: 9, fontWeight: FontWeight.w800, letterSpacing: 1.2)),
                    ],
                  ),
                ),
                destinations: const [
                  NavigationRailDestination(
                    icon: Icon(Icons.verified_user_outlined),
                    selectedIcon: Icon(Icons.verified_user_rounded),
                    label: Text('Verify'),
                  ),
                  NavigationRailDestination(
                    icon: Icon(Icons.access_time_outlined),
                    selectedIcon: Icon(Icons.access_time_filled),
                    label: Text('Provenance'),
                  ),
                  NavigationRailDestination(
                    icon: Icon(Icons.account_balance_wallet_outlined),
                    selectedIcon: Icon(Icons.account_balance_wallet_rounded),
                    label: Text('Wallet'),
                  ),
                  NavigationRailDestination(
                    icon: Icon(Icons.storefront_outlined),
                    selectedIcon: Icon(Icons.storefront_rounded),
                    label: Text('Market'),
                  ),
                  NavigationRailDestination(
                    icon: Icon(Icons.account_balance_outlined),
                    selectedIcon: Icon(Icons.account_balance_rounded),
                    label: Text('Gallery Safe'),
                  ),
                  NavigationRailDestination(
                    icon: Icon(Icons.biotech_outlined),
                    selectedIcon: Icon(Icons.biotech_rounded),
                    label: Text('Conservator'),
                  ),
                  NavigationRailDestination(
                    icon: Icon(Icons.shield_outlined),
                    selectedIcon: Icon(Icons.shield_rounded),
                    label: Text('Governance'),
                  ),
                ],
              ),
              const VerticalDivider(width: 1, thickness: 1, color: Color(0xFFE2E8F0)),
              Expanded(
                child: IndexedStack(
                  index: _currentIndex < desktopScreens.length ? _currentIndex : 0,
                  children: desktopScreens,
                ),
              ),
            ],
          ),
        ),
      );
    }

    // Compact Mobile View (< 900px) on iOS
    return AppLockGate(
      child: Scaffold(
        body: IndexedStack(
          index: _currentIndex < standardScreens.length ? _currentIndex : 0,
          children: standardScreens,
        ),
        bottomNavigationBar: Container(
          decoration: BoxDecoration(
            color: Colors.white,
            border: Border(top: BorderSide(color: AppTheme.borderLight, width: 0.8)),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withOpacity(0.02),
                blurRadius: 8,
                offset: const Offset(0, -2),
              ),
            ],
          ),
          child: BottomNavigationBar(
            type: BottomNavigationBarType.fixed,
            currentIndex: _currentIndex < standardScreens.length ? _currentIndex : 0,
            onTap: _onTabSelected,
            elevation: 0,
            backgroundColor: Colors.white,
            selectedItemColor: AppTheme.brandBlue,
            unselectedItemColor: const Color(0xFF6B7280),
            selectedLabelStyle: GoogleFonts.inter(fontSize: 12, fontWeight: FontWeight.w600),
            unselectedLabelStyle: GoogleFonts.inter(fontSize: 12, fontWeight: FontWeight.w500),
            items: const [
              BottomNavigationBarItem(
                icon: Icon(Icons.verified_user_outlined),
                activeIcon: Icon(Icons.verified_user_rounded),
                label: 'Verify',
              ),
              BottomNavigationBarItem(
                icon: Icon(Icons.access_time_outlined),
                activeIcon: Icon(Icons.access_time_filled),
                label: 'Provenance',
              ),
              BottomNavigationBarItem(
                icon: Icon(Icons.account_balance_wallet_outlined),
                activeIcon: Icon(Icons.account_balance_wallet_rounded),
                label: 'Wallet',
              ),
              BottomNavigationBarItem(
                icon: Icon(Icons.storefront_outlined),
                activeIcon: Icon(Icons.storefront_rounded),
                label: 'Market',
              ),
            ],
          ),
        ),
      ),
    );
  }
}
