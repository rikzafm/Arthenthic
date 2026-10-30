import 'dart:convert';
import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../core/theme.dart';
import '../../contracts/contract_config.dart';
import '../../capture/capture_channel.dart';
import '../../services/api_client.dart';
import '../../services/wallet_service.dart';
import '../shared/artistic_background.dart';

class MarketplaceScreen extends StatefulWidget {
  const MarketplaceScreen({super.key});

  @override
  State<MarketplaceScreen> createState() => _MarketplaceScreenState();
}

class _MarketplaceScreenState extends State<MarketplaceScreen> {
  List<Map<String, dynamic>> _listings = [];
  bool _isLoading = true;
  String _selectedFilter = "ALL"; // ALL, USDC, ETH, ESCROW
  bool _hasProLidarHardware = true; // A6: Tiered Hardware Fallback toggle for demoing Pro vs Standard phone

  // Per-escrow local verification step state for interactive demo
  final Set<String> _l1TappedEscrows = {};
  final Set<String> _l2ScannedEscrows = {};

  @override
  void initState() {
    super.initState();
    _loadListings();
  }

  Future<void> _loadListings() async {
    setState(() => _isLoading = true);
    final items = await apiClient.getMarketplaceListings();
    if (mounted) {
      setState(() {
        _listings = items;
        _isLoading = false;
      });
    }
  }

  List<Map<String, dynamic>> get _filteredListings {
    if (_selectedFilter == "USDC") {
      return _listings.where((l) => l["asset"] == "USDC").toList();
    } else if (_selectedFilter == "ETH") {
      return _listings.where((l) => l["asset"] == "ETH").toList();
    } else if (_selectedFilter == "ESCROW") {
      return _listings.where((l) => l["active_escrow"] != null).toList();
    }
    return _listings;
  }

  // ---------------------------------------------------------------------------
  // Base L2 DEX Swap Modal (Aerodrome / Uniswap v3 Pool ETH <-> USDC)
  // ---------------------------------------------------------------------------

  void _showDexSwapModal({String initialFrom = "ETH", String initialTo = "USDC", double? initialAmount}) {
    String fromAsset = initialFrom;
    String toAsset = initialTo;
    final amountCtrl = TextEditingController(text: (initialAmount ?? (fromAsset == "ETH" ? 1.0 : 3000.0)).toString());
    int selectedSlippageBps = 50; // 0.5%
    bool isSwapping = false;

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (ctx) {
        return StatefulBuilder(
          builder: (context, setModalState) {
            final inAmount = double.tryParse(amountCtrl.text.trim()) ?? 0.0;
            const rate = 3000.0; // 1 ETH = 3,000 USDC
            double outAmount = 0.0;
            if (fromAsset == "ETH" && toAsset == "USDC") {
              outAmount = inAmount * rate;
            } else {
              outAmount = inAmount > 0 ? inAmount / rate : 0.0;
            }
            final minOut = outAmount * (1.0 - (selectedSlippageBps / 10000.0));

            return Padding(
              padding: EdgeInsets.only(
                left: 24,
                right: 24,
                top: 20,
                bottom: MediaQuery.of(context).viewInsets.bottom + 24,
              ),
              child: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Row(
                          children: [
                            Container(
                              padding: const EdgeInsets.all(8),
                              decoration: BoxDecoration(
                                color: const Color(0xFFEFF6FF),
                                borderRadius: BorderRadius.circular(10),
                              ),
                              child: const Icon(Icons.swap_horiz_rounded, color: Color(0xFF2563EB), size: 22),
                            ),
                            const SizedBox(width: 10),
                            Text(
                              "Base L2 DEX Swap",
                              style: GoogleFonts.inter(fontSize: 18, fontWeight: FontWeight.w700),
                            ),
                          ],
                        ),
                        IconButton(
                          icon: const Icon(Icons.close, size: 20),
                          onPressed: () => Navigator.pop(ctx),
                        ),
                      ],
                    ),
                    const SizedBox(height: 4),
                    Text(
                      "Instant liquidity via Aerodrome / Uniswap v3 Pool on Base Sepolia. Zero bridge latency.",
                      style: GoogleFonts.inter(fontSize: 12.5, color: AppTheme.textSecondary),
                    ),
                    const SizedBox(height: 18),

                    // From Asset Input Box
                    Container(
                      padding: const EdgeInsets.all(14),
                      decoration: BoxDecoration(
                        color: const Color(0xFFF8FAFC),
                        borderRadius: BorderRadius.circular(16),
                        border: Border.all(color: AppTheme.borderLight),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              Text("You Pay", style: GoogleFonts.inter(fontSize: 12, color: AppTheme.textSecondary)),
                              Text("Balance: 12.45 $fromAsset", style: GoogleFonts.sourceCodePro(fontSize: 11, color: AppTheme.textMuted)),
                            ],
                          ),
                          const SizedBox(height: 6),
                          Row(
                            children: [
                              Expanded(
                                child: TextField(
                                  controller: amountCtrl,
                                  keyboardType: const TextInputType.numberWithOptions(decimal: true),
                                  style: GoogleFonts.sourceCodePro(fontSize: 20, fontWeight: FontWeight.w700),
                                  onChanged: (_) => setModalState(() {}),
                                  decoration: const InputDecoration(
                                    isDense: true,
                                    contentPadding: EdgeInsets.zero,
                                    border: InputBorder.none,
                                    hintText: "0.0",
                                  ),
                                ),
                              ),
                              Container(
                                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                                decoration: BoxDecoration(
                                  color: Colors.white,
                                  borderRadius: BorderRadius.circular(12),
                                  border: Border.all(color: AppTheme.borderLight),
                                ),
                                child: Text(
                                  fromAsset,
                                  style: GoogleFonts.inter(fontWeight: FontWeight.w700, fontSize: 13),
                                ),
                              ),
                            ],
                          ),
                        ],
                      ),
                    ),

                    // Invert Swap Button
                    Center(
                      child: Padding(
                        padding: const EdgeInsets.symmetric(vertical: 8),
                        child: InkWell(
                          onTap: () {
                            setModalState(() {
                              final temp = fromAsset;
                              fromAsset = toAsset;
                              toAsset = temp;
                              amountCtrl.text = outAmount > 0 ? (fromAsset == "ETH" ? (outAmount / 3000).toStringAsFixed(3) : (outAmount * 3000).toStringAsFixed(1)) : "1.0";
                            });
                          },
                          borderRadius: BorderRadius.circular(20),
                          child: Container(
                            padding: const EdgeInsets.all(8),
                            decoration: BoxDecoration(
                              color: Colors.white,
                              shape: BoxShape.circle,
                              border: Border.all(color: AppTheme.borderLight),
                              boxShadow: [
                                BoxShadow(color: Colors.black.withValues(alpha: 0.04), blurRadius: 6),
                              ],
                            ),
                            child: const Icon(Icons.arrow_downward_rounded, size: 18, color: AppTheme.brandDark),
                          ),
                        ),
                      ),
                    ),

                    // To Asset Output Box
                    Container(
                      padding: const EdgeInsets.all(14),
                      decoration: BoxDecoration(
                        color: const Color(0xFFF8FAFC),
                        borderRadius: BorderRadius.circular(16),
                        border: Border.all(color: AppTheme.borderLight),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              Text("You Receive (Estimated)", style: GoogleFonts.inter(fontSize: 12, color: AppTheme.textSecondary)),
                              Text("~$outAmount $toAsset", style: GoogleFonts.sourceCodePro(fontSize: 11, color: AppTheme.brandBlue, fontWeight: FontWeight.w700)),
                            ],
                          ),
                          const SizedBox(height: 6),
                          Row(
                            children: [
                              Expanded(
                                child: Text(
                                  toAsset == "USDC" ? outAmount.toStringAsFixed(2) : outAmount.toStringAsFixed(5),
                                  style: GoogleFonts.sourceCodePro(fontSize: 20, fontWeight: FontWeight.w700, color: AppTheme.textPrimary),
                                ),
                              ),
                              Container(
                                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                                decoration: BoxDecoration(
                                  color: Colors.white,
                                  borderRadius: BorderRadius.circular(12),
                                  border: Border.all(color: AppTheme.borderLight),
                                ),
                                child: Text(
                                  toAsset,
                                  style: GoogleFonts.inter(fontWeight: FontWeight.w700, fontSize: 13),
                                ),
                              ),
                            ],
                          ),
                        ],
                      ),
                    ),

                    const SizedBox(height: 14),

                    // Slippage Selector
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Text("Slippage Tolerance", style: GoogleFonts.inter(fontSize: 12, color: AppTheme.textSecondary)),
                        Row(
                          children: [10, 50, 100].map((bps) {
                            final isSel = selectedSlippageBps == bps;
                            return GestureDetector(
                              onTap: () => setModalState(() => selectedSlippageBps = bps),
                              child: Container(
                                margin: const EdgeInsets.only(left: 6),
                                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                                decoration: BoxDecoration(
                                  color: isSel ? AppTheme.brandDark : const Color(0xFFF1F5F9),
                                  borderRadius: BorderRadius.circular(8),
                                ),
                                child: Text(
                                  "${bps / 100}%",
                                  style: GoogleFonts.inter(
                                    fontSize: 11,
                                    fontWeight: isSel ? FontWeight.w700 : FontWeight.w500,
                                    color: isSel ? Colors.white : AppTheme.textSecondary,
                                  ),
                                ),
                              ),
                            );
                          }).toList(),
                        ),
                      ],
                    ),

                    const SizedBox(height: 12),

                    // Route & Pool Details
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: const Color(0xFFF1F5F9),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Column(
                        children: [
                          _buildSplitRow("Rate", "1 ETH = 3,000.00 USDC", AppTheme.textPrimary),
                          _buildSplitRow("Minimum Received", "${toAsset == "USDC" ? minOut.toStringAsFixed(2) : minOut.toStringAsFixed(5)} $toAsset", const Color(0xFF065F46)),
                          _buildSplitRow("Estimated Base L2 Gas", r"~$0.012 (0.000035 ETH)", const Color(0xFF92400E)),
                          _buildSplitRow("Liquidity Route", "Aerodrome WETH/USDC 0.05% AMM", AppTheme.brandBlue),
                        ],
                      ),
                    ),

                    const SizedBox(height: 18),

                    SizedBox(
                      width: double.infinity,
                      height: 48,
                      child: ElevatedButton.icon(
                        onPressed: isSwapping || inAmount <= 0
                            ? null
                            : () async {
                                setModalState(() => isSwapping = true);
                                final res = await apiClient.executeSwap(
                                  callerWallet: walletService.address,
                                  fromAsset: fromAsset,
                                  toAsset: toAsset,
                                  inAmount: inAmount,
                                  minOutAmount: minOut,
                                  slippageBps: selectedSlippageBps,
                                );
                                walletService.recordSignature(
                                  "[Base L2 DEX Swap] Swapped $inAmount $fromAsset -> ${res['swapped']?['received'] ?? '$outAmount $toAsset'}",
                                );
                                if (mounted) {
                                  Navigator.pop(ctx);
                                  ScaffoldMessenger.of(context).showSnackBar(
                                    SnackBar(
                                      backgroundColor: const Color(0xFF065F46),
                                      content: Text(
                                        "Swap Confirmed! Received ${toAsset == 'USDC' ? outAmount.toStringAsFixed(2) : outAmount.toStringAsFixed(5)} $toAsset via Aerodrome Base L2.",
                                      ),
                                    ),
                                  );
                                }
                              },
                        icon: const Icon(Icons.currency_exchange_rounded, size: 18),
                        label: Text(
                          isSwapping ? "Executing DEX Swap on Base L2..." : "Swap $fromAsset to $toAsset",
                          style: GoogleFonts.inter(fontWeight: FontWeight.w600),
                        ),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: AppTheme.brandBlue,
                          foregroundColor: Colors.white,
                          elevation: 0,
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            );
          },
        );
      },
    );
  }

  // ---------------------------------------------------------------------------
  // Create Listing Modal (C-01) with Camera Capture & Painting Photo Upload
  // ---------------------------------------------------------------------------

  void _showCreateListingModal() {
    final titleCtrl = TextEditingController(text: "Study in Ochre & Cobalt #14");
    final artistCtrl = TextEditingController(text: "Studio Arthentic");
    final priceCtrl = TextEditingController(text: "15000");
    final mediumCtrl = TextEditingController(text: "Oil, lapis pigment & dammar varnish on linen");
    final dimCtrl = TextEditingController(text: "115 x 85 cm");
    final imgCtrl = TextEditingController(text: "https://images.unsplash.com/photo-1579783900882-c0d3dad7b119?auto=format&fit=crop&w=1200&q=80");
    String selectedAsset = "USDC";
    Uint8List? capturedPhotoBytes;
    bool isCapturingPhoto = false;
    bool isSubmitting = false;

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (ctx) {
        return StatefulBuilder(
          builder: (context, setModalState) {
            final priceVal = double.tryParse(priceCtrl.text.trim()) ?? 0.0;
            final artistRoyalty = priceVal * 0.05;
            final platformFee = priceVal * 0.015;
            final sellerNet = priceVal - artistRoyalty - platformFee;

            return Padding(
              padding: EdgeInsets.only(
                left: 24,
                right: 24,
                top: 20,
                bottom: MediaQuery.of(context).viewInsets.bottom + 24,
              ),
              child: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Text(
                          "Curate & List Artwork (C-01)",
                          style: GoogleFonts.newsreader(fontSize: 22, fontWeight: FontWeight.w700, fontStyle: FontStyle.italic),
                        ),
                        IconButton(
                          icon: const Icon(Icons.close, size: 20),
                          onPressed: () => Navigator.pop(ctx),
                        ),
                      ],
                    ),
                    const SizedBox(height: 4),
                    Text(
                      "A1 Hybrid Meta-Tx Relayer: Gasless EIP-712 ListingIntent signed with ${walletService.walletProvider}.",
                      style: GoogleFonts.inter(fontSize: 12.5, color: AppTheme.textSecondary),
                    ),
                    const SizedBox(height: 16),

                    // Painting Photo / Camera Capture Card
                    Text("Painting Photo & Canvas Preview", style: GoogleFonts.inter(fontSize: 12.5, fontWeight: FontWeight.w600)),
                    const SizedBox(height: 6),
                    Container(
                      width: double.infinity,
                      decoration: BoxDecoration(
                        color: const Color(0xFF1E1E24),
                        borderRadius: BorderRadius.circular(16),
                        border: Border.all(color: const Color(0xFFD4AF37).withValues(alpha: 0.3)),
                      ),
                      padding: const EdgeInsets.all(8),
                      child: Column(
                        children: [
                          ClipRRect(
                            borderRadius: BorderRadius.circular(10),
                            child: AspectRatio(
                              aspectRatio: 16 / 9,
                              child: Stack(
                                fit: StackFit.expand,
                                children: [
                                  if (capturedPhotoBytes != null)
                                    Image.memory(capturedPhotoBytes!, fit: BoxFit.cover)
                                  else if (imgCtrl.text.trim().startsWith("http"))
                                    Image.network(
                                      imgCtrl.text.trim(),
                                      fit: BoxFit.cover,
                                      errorBuilder: (_, __, ___) => _buildProceduralStandInCanvas(
                                        titleCtrl.text.isEmpty ? "Untitled" : titleCtrl.text,
                                        artistCtrl.text.isEmpty ? "Artist" : artistCtrl.text,
                                      ),
                                    )
                                  else
                                    _buildProceduralStandInCanvas(
                                      titleCtrl.text.isEmpty ? "Untitled" : titleCtrl.text,
                                      artistCtrl.text.isEmpty ? "Artist" : artistCtrl.text,
                                    ),
                                  // Overlay Badge
                                  Positioned(
                                    top: 8,
                                    left: 8,
                                    child: Container(
                                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                                      decoration: BoxDecoration(
                                        color: Colors.black.withValues(alpha: 0.65),
                                        borderRadius: BorderRadius.circular(12),
                                      ),
                                      child: Row(
                                        mainAxisSize: MainAxisSize.min,
                                        children: [
                                          Icon(
                                            capturedPhotoBytes != null ? Icons.camera_alt_rounded : Icons.photo_library_outlined,
                                            color: AppTheme.bubbleYellow,
                                            size: 12,
                                          ),
                                          const SizedBox(width: 4),
                                          Text(
                                            capturedPhotoBytes != null ? "CAMERA PHOTO READY" : "GALLERY PREVIEW",
                                            style: GoogleFonts.inter(fontSize: 9.5, fontWeight: FontWeight.w700, color: Colors.white),
                                          ),
                                        ],
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ),
                          const SizedBox(height: 8),
                          // Camera and Preset Action Buttons
                          Row(
                            children: [
                              Expanded(
                                child: ElevatedButton.icon(
                                  onPressed: isCapturingPhoto
                                      ? null
                                      : () async {
                                          setModalState(() => isCapturingPhoto = true);
                                          try {
                                            final cap = await CaptureChannel.capturePoint(1);
                                            final bytes = cap['photoBytes'] as Uint8List?;
                                            if (bytes != null && bytes.isNotEmpty) {
                                              setModalState(() {
                                                capturedPhotoBytes = bytes;
                                                imgCtrl.text = ""; // Clear URL to prioritize camera bytes
                                              });
                                            }
                                          } catch (_) {} finally {
                                            setModalState(() => isCapturingPhoto = false);
                                          }
                                        },
                                  icon: const Icon(Icons.camera_alt_rounded, size: 16),
                                  label: Text(
                                    capturedPhotoBytes != null ? "Retake Photo" : "Take Photo (Camera)",
                                    style: GoogleFonts.inter(fontSize: 12, fontWeight: FontWeight.w600),
                                  ),
                                  style: ElevatedButton.styleFrom(
                                    backgroundColor: const Color(0xFFD4AF37),
                                    foregroundColor: Colors.black,
                                    elevation: 0,
                                    padding: const EdgeInsets.symmetric(vertical: 8),
                                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                                  ),
                                ),
                              ),
                              const SizedBox(width: 8),
                              OutlinedButton.icon(
                                onPressed: () {
                                  // Quick-select preset
                                  setModalState(() {
                                    capturedPhotoBytes = null;
                                    imgCtrl.text = "https://images.unsplash.com/photo-1541701494587-cb58502866ab?auto=format&fit=crop&w=1200&q=80";
                                    titleCtrl.text = "Geometric Cadmium Relief #8";
                                    mediumCtrl.text = "Cadmium crimson impasto and beeswax on linen";
                                    dimCtrl.text = "140 x 110 cm";
                                  });
                                },
                                icon: const Icon(Icons.auto_awesome_rounded, size: 15, color: Colors.white70),
                                label: Text("Sample Art", style: GoogleFonts.inter(fontSize: 12, color: Colors.white)),
                                style: OutlinedButton.styleFrom(
                                  side: BorderSide(color: Colors.white.withValues(alpha: 0.3)),
                                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                                ),
                              ),
                            ],
                          ),
                        ],
                      ),
                    ),

                    const SizedBox(height: 14),
                    Text("Artwork Title", style: GoogleFonts.inter(fontSize: 12.5, fontWeight: FontWeight.w600)),
                    const SizedBox(height: 6),
                    TextField(
                      controller: titleCtrl,
                      onChanged: (_) => setModalState(() {}),
                      decoration: InputDecoration(
                        filled: true,
                        fillColor: const Color(0xFFF8FAFC),
                        contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(12),
                          borderSide: const BorderSide(color: AppTheme.borderLight),
                        ),
                      ),
                    ),
                    const SizedBox(height: 12),
                    Row(
                      children: [
                        Expanded(
                          flex: 3,
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text("Price Amount", style: GoogleFonts.inter(fontSize: 12.5, fontWeight: FontWeight.w600)),
                              const SizedBox(height: 6),
                              TextField(
                                controller: priceCtrl,
                                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                                onChanged: (_) => setModalState(() {}),
                                decoration: InputDecoration(
                                  filled: true,
                                  fillColor: const Color(0xFFF8FAFC),
                                  contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                                  border: OutlineInputBorder(
                                    borderRadius: BorderRadius.circular(12),
                                    borderSide: const BorderSide(color: AppTheme.borderLight),
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          flex: 2,
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text("Asset (A4)", style: GoogleFonts.inter(fontSize: 12.5, fontWeight: FontWeight.w600)),
                              const SizedBox(height: 6),
                              DropdownButtonFormField<String>(
                                initialValue: selectedAsset,
                                decoration: InputDecoration(
                                  filled: true,
                                  fillColor: const Color(0xFFF8FAFC),
                                  contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
                                  border: OutlineInputBorder(
                                    borderRadius: BorderRadius.circular(12),
                                    borderSide: const BorderSide(color: AppTheme.borderLight),
                                  ),
                                ),
                                items: const [
                                  DropdownMenuItem(value: "USDC", child: Text("USDC")),
                                  DropdownMenuItem(value: "ETH", child: Text("ETH")),
                                ],
                                onChanged: (val) {
                                  if (val != null) setModalState(() => selectedAsset = val);
                                },
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 12),
                    Text("Medium & Technique", style: GoogleFonts.inter(fontSize: 12.5, fontWeight: FontWeight.w600)),
                    const SizedBox(height: 6),
                    TextField(
                      controller: mediumCtrl,
                      decoration: InputDecoration(
                        filled: true,
                        fillColor: const Color(0xFFF8FAFC),
                        contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(12),
                          borderSide: const BorderSide(color: AppTheme.borderLight),
                        ),
                      ),
                    ),
                    const SizedBox(height: 12),
                    Text("Dimensions (cm)", style: GoogleFonts.inter(fontSize: 12.5, fontWeight: FontWeight.w600)),
                    const SizedBox(height: 6),
                    TextField(
                      controller: dimCtrl,
                      decoration: InputDecoration(
                        filled: true,
                        fillColor: const Color(0xFFF8FAFC),
                        contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(12),
                          borderSide: const BorderSide(color: AppTheme.borderLight),
                        ),
                      ),
                    ),
                    const SizedBox(height: 12),
                    Text("Or enter Painting Image URL", style: GoogleFonts.inter(fontSize: 12.5, fontWeight: FontWeight.w600)),
                    const SizedBox(height: 6),
                    TextField(
                      controller: imgCtrl,
                      onChanged: (_) => setModalState(() {}),
                      decoration: InputDecoration(
                        hintText: "https://... (or use camera / stand-in canvas above)",
                        hintStyle: GoogleFonts.inter(fontSize: 12, color: AppTheme.textMuted),
                        filled: true,
                        fillColor: const Color(0xFFF8FAFC),
                        contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(12),
                          borderSide: const BorderSide(color: AppTheme.borderLight),
                        ),
                      ),
                    ),
                    const SizedBox(height: 14),
                    // Live A5 3-Way Split Preview
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: const Color(0xFFF8FAFC),
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: AppTheme.borderLight),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            "A5 On-Chain 3-Way Escrow Split Preview",
                            style: GoogleFonts.inter(fontSize: 12, fontWeight: FontWeight.w700, color: AppTheme.textPrimary),
                          ),
                          const SizedBox(height: 6),
                          _buildSplitRow("Seller Net Payout (93.5%)", "${sellerNet.toStringAsFixed(2)} $selectedAsset", const Color(0xFF065F46)),
                          _buildSplitRow("Artist Royalty ERC-2981 (5.0%)", "${artistRoyalty.toStringAsFixed(2)} $selectedAsset", AppTheme.brandBlue),
                          _buildSplitRow("Arthentic Treasury Safe (1.5%)", "${platformFee.toStringAsFixed(2)} $selectedAsset", const Color(0xFF92400E)),
                        ],
                      ),
                    ),
                    const SizedBox(height: 18),
                    SizedBox(
                      width: double.infinity,
                      height: 48,
                      child: ElevatedButton.icon(
                        onPressed: isSubmitting
                            ? null
                            : () async {
                                setModalState(() => isSubmitting = true);
                                String? finalImageUrl = imgCtrl.text.trim().isNotEmpty ? imgCtrl.text.trim() : null;

                                // If camera photo was captured, upload or encode it
                                if (capturedPhotoBytes != null) {
                                  final uploadedUrl = await apiClient.uploadListingImage(
                                    capturedPhotoBytes!,
                                    filename: "canvas_${DateTime.now().millisecondsSinceEpoch}.jpg",
                                  );
                                  if (uploadedUrl != null) {
                                    finalImageUrl = uploadedUrl;
                                  }
                                }

                                final sig = "0xmetamask_c01_intent_${DateTime.now().millisecondsSinceEpoch}";
                                walletService.recordSignature("[MetaMask C-01] Listed '${titleCtrl.text.trim()}' for ${priceCtrl.text} $selectedAsset with Camera/Uploaded Photo");
                                await apiClient.createMarketplaceListing(
                                  artworkTitle: titleCtrl.text.trim(),
                                  artistName: artistCtrl.text.trim(),
                                  sellerWallet: walletService.address,
                                  priceAmount: priceVal > 0 ? priceVal : 1000.0,
                                  asset: selectedAsset,
                                  imageUrl: finalImageUrl,
                                  medium: mediumCtrl.text.trim(),
                                  dimensions: dimCtrl.text.trim(),
                                  year: 2024,
                                  signature: sig,
                                );
                                if (mounted) {
                                  Navigator.pop(ctx);
                                  _loadListings();
                                  ScaffoldMessenger.of(context).showSnackBar(
                                    SnackBar(
                                      backgroundColor: AppTheme.brandDark,
                                      content: Text("Artwork listed with photo via gasless EIP-712 Meta-Tx ($selectedAsset)!"),
                                    ),
                                  );
                                }
                              },
                        icon: const Icon(Icons.bolt_rounded, size: 18),
                        label: Text(
                          isSubmitting ? "Uploading Photo & Signing..." : "Sign & Publish to Gallery (Gasless)",
                          style: GoogleFonts.inter(fontWeight: FontWeight.w600),
                        ),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: AppTheme.brandDark,
                          foregroundColor: Colors.white,
                          elevation: 0,
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            );
          },
        );
      },
    );
  }

  // ---------------------------------------------------------------------------
  // Deposit Escrow Sheet (C-04) with Integrated DEX Swap Option
  // ---------------------------------------------------------------------------

  void _showDepositEscrowSheet(Map<String, dynamic> listing) {
    final asset = (listing["asset"] ?? "USDC").toString();
    final price = listing["price_amount"] ?? 0.0;
    final split = listing["split_breakdown"] as Map<String, dynamic>? ?? {};
    bool permitSigned = asset != "USDC";
    bool isSubmitting = false;
    bool payWithSwap = false; // Toggle to pay with the other currency via Base L2 DEX

    final otherAsset = asset == "USDC" ? "ETH" : "USDC";
    final swapInAmount = asset == "USDC" ? (price / 3000.0) : (price * 3000.0);

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (ctx) {
        return StatefulBuilder(
          builder: (context, setModalState) {
            return Padding(
              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 22),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                        decoration: BoxDecoration(
                          color: const Color(0xFFFFF7ED),
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(color: const Color(0xFFF97316).withValues(alpha: 0.4)),
                        ),
                        child: Text(
                          "SD-03 · C-04 ESCROW DEPOSIT",
                          style: GoogleFonts.sourceCodePro(
                            fontSize: 11,
                            fontWeight: FontWeight.w700,
                            color: const Color(0xFFC2410C),
                          ),
                        ),
                      ),
                      IconButton(
                        icon: const Icon(Icons.close, size: 20),
                        onPressed: () => Navigator.pop(ctx),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Text(
                    payWithSwap
                        ? "Swap $swapInAmount $otherAsset & Lock in Escrow"
                        : "Lock $price $asset in ArthenticEscrow",
                    style: GoogleFonts.inter(fontSize: 18, fontWeight: FontWeight.w700, color: AppTheme.textPrimary),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    "Funds remain cryptographically locked in ArthenticEscrow.sol until you physically receive the canvas and pass L1 NFC + L2 Pro LiDAR verification (SD-04).",
                    style: GoogleFonts.inter(fontSize: 12.5, color: AppTheme.textSecondary, height: 1.35),
                  ),
                  const SizedBox(height: 12),

                  // Pay Direct vs Swap & Pay Selector
                  Container(
                    padding: const EdgeInsets.all(4),
                    decoration: BoxDecoration(
                      color: const Color(0xFFF1F5F9),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Row(
                      children: [
                        Expanded(
                          child: GestureDetector(
                            onTap: () => setModalState(() => payWithSwap = false),
                            child: Container(
                              padding: const EdgeInsets.symmetric(vertical: 8),
                              decoration: BoxDecoration(
                                color: !payWithSwap ? Colors.white : Colors.transparent,
                                borderRadius: BorderRadius.circular(10),
                                boxShadow: !payWithSwap ? [BoxShadow(color: Colors.black.withValues(alpha: 0.04), blurRadius: 4)] : null,
                              ),
                              child: Center(
                                child: Text(
                                  "Pay in $asset",
                                  style: GoogleFonts.inter(
                                    fontSize: 12,
                                    fontWeight: !payWithSwap ? FontWeight.w700 : FontWeight.w500,
                                    color: !payWithSwap ? AppTheme.textPrimary : AppTheme.textSecondary,
                                  ),
                                ),
                              ),
                            ),
                          ),
                        ),
                        Expanded(
                          child: GestureDetector(
                            onTap: () => setModalState(() => payWithSwap = true),
                            child: Container(
                              padding: const EdgeInsets.symmetric(vertical: 8),
                              decoration: BoxDecoration(
                                color: payWithSwap ? Colors.white : Colors.transparent,
                                borderRadius: BorderRadius.circular(10),
                                boxShadow: payWithSwap ? [BoxShadow(color: Colors.black.withValues(alpha: 0.04), blurRadius: 4)] : null,
                              ),
                              child: Center(
                                child: Text(
                                  "Swap from $otherAsset",
                                  style: GoogleFonts.inter(
                                    fontSize: 12,
                                    fontWeight: payWithSwap ? FontWeight.w700 : FontWeight.w500,
                                    color: payWithSwap ? AppTheme.brandBlue : AppTheme.textSecondary,
                                  ),
                                ),
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),

                  const SizedBox(height: 14),

                  if (payWithSwap) ...[
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: const Color(0xFFEFF6FF),
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: const Color(0xFF93C5FD)),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              const Icon(Icons.auto_awesome_rounded, color: Color(0xFF2563EB), size: 16),
                              const SizedBox(width: 6),
                              Text(
                                "Aerodrome 1-Click Swap & Deposit",
                                style: GoogleFonts.inter(fontSize: 12, fontWeight: FontWeight.w700, color: const Color(0xFF1E40AF)),
                              ),
                            ],
                          ),
                          const SizedBox(height: 6),
                          Text(
                            "Your wallet provides $swapInAmount $otherAsset. The Base L2 router converts it into $price $asset and deposits directly into ArthenticEscrow.",
                            style: GoogleFonts.inter(fontSize: 11.5, color: const Color(0xFF1E3A8A)),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 12),
                  ],

                  Container(
                    padding: const EdgeInsets.all(14),
                    decoration: BoxDecoration(
                      color: const Color(0xFFF8FAFC),
                      borderRadius: BorderRadius.circular(14),
                      border: Border.all(color: AppTheme.borderLight),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        _buildSplitRow("Active Wallet", "${walletService.walletProvider} (${walletService.shortAddress})", AppTheme.textPrimary),
                        _buildSplitRow(
                          "Gas Policy (A1)",
                          walletService.walletProvider.startsWith("MetaMask")
                              ? r"Self-Pay Base L2 ETH (~$0.01)"
                              : "ERC-4337 Paymaster Sponsored",
                          const Color(0xFFC2410C),
                        ),
                        const Divider(height: 16),
                        _buildSplitRow("93.5% Seller Net", "${split['seller_payout_amount']} $asset", const Color(0xFF065F46)),
                        _buildSplitRow("5.0% Artist Royalty (ERC-2981)", "${split['artist_royalty_amount']} $asset", AppTheme.brandBlue),
                        _buildSplitRow("1.5% Platform Treasury Safe", "${split['platform_fee_amount']} $asset", const Color(0xFF92400E)),
                      ],
                    ),
                  ),
                  const SizedBox(height: 14),
                  if (asset == "USDC" && !payWithSwap) ...[
                    InkWell(
                      onTap: () => setModalState(() => permitSigned = !permitSigned),
                      borderRadius: BorderRadius.circular(12),
                      child: Container(
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: permitSigned ? const Color(0xFFECFDF5) : const Color(0xFFFFFBEB),
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(
                            color: permitSigned ? const Color(0xFF10B981) : const Color(0xFFF59E0B),
                          ),
                        ),
                        child: Row(
                          children: [
                            Icon(
                              permitSigned ? Icons.verified_rounded : Icons.draw_outlined,
                              color: permitSigned ? const Color(0xFF059669) : const Color(0xFFD97706),
                              size: 20,
                            ),
                            const SizedBox(width: 10),
                            Expanded(
                              child: Text(
                                permitSigned
                                    ? "Step 1 Complete: EIP-2612 / Permit2 Gasless USDC Allowance Signed"
                                    : "Step 1: Tap to Sign Gasless Permit2 USDC Allowance in MetaMask",
                                style: GoogleFonts.inter(
                                  fontSize: 12.5,
                                  fontWeight: FontWeight.w600,
                                  color: permitSigned ? const Color(0xFF065F46) : const Color(0xFF92400E),
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(height: 14),
                  ],
                  SizedBox(
                    width: double.infinity,
                    height: 48,
                    child: ElevatedButton.icon(
                      onPressed: (!permitSigned && !payWithSwap) || isSubmitting
                          ? null
                          : () async {
                              setModalState(() => isSubmitting = true);
                              final providerStr = walletService.walletProvider.startsWith("MetaMask")
                                  ? "metamask"
                                  : "smart_wallet";

                              Map<String, dynamic> res;
                              if (payWithSwap) {
                                res = await apiClient.swapAndDepositEscrow(
                                  listingId: listing["id"],
                                  buyerWallet: walletService.address,
                                  fromAsset: otherAsset,
                                  inAmount: swapInAmount,
                                  walletProvider: providerStr,
                                );
                                walletService.recordSignature(
                                  "[Base L2 Swap & Escrow] Swapped $swapInAmount $otherAsset -> $price $asset & locked in ArthenticEscrow",
                                );
                              } else {
                                res = await apiClient.depositEscrow(
                                  listingId: listing["id"],
                                  buyerWallet: walletService.address,
                                  walletProvider: providerStr,
                                  permit2Signature: asset == "USDC" ? "0xpermit2_eip2612_signed_allowance" : null,
                                );
                                walletService.recordSignature(
                                  "[MetaMask C-04] Deposited $price $asset into ArthenticEscrow (${listing['artwork_title']})",
                                );
                              }

                              if (mounted) {
                                Navigator.pop(ctx);
                                _loadListings();
                                ScaffoldMessenger.of(context).showSnackBar(
                                  SnackBar(
                                    backgroundColor: AppTheme.brandDark,
                                    content: Text(
                                      res["success"] == true
                                          ? (payWithSwap
                                              ? "Swap & Escrow Complete! Converted $otherAsset to $price $asset and locked in vault."
                                              : "Escrow Locked! $price $asset held in ArthenticEscrow until physical L1+L2 delivery.")
                                          : (res["error"] ?? "Escrow deposit failed"),
                                    ),
                                  ),
                                );
                              }
                            },
                      icon: const Icon(Icons.lock_outline_rounded, size: 18),
                      label: Text(
                        isSubmitting
                            ? "Broadcasting Escrow Tx..."
                            : (payWithSwap
                                ? "Swap & Lock in Escrow"
                                : "Sign & Lock $price $asset in Escrow"),
                        style: GoogleFonts.inter(fontWeight: FontWeight.w600),
                      ),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: const Color(0xFFE65100),
                        foregroundColor: Colors.white,
                        elevation: 0,
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                      ),
                    ),
                  ),
                ],
              ),
            );
          },
        );
      },
    );
  }

  Widget _buildSplitRow(String label, String value, Color valueColor) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: GoogleFonts.inter(fontSize: 12, color: AppTheme.textSecondary)),
          Flexible(
            child: Text(
              value,
              textAlign: TextAlign.right,
              style: GoogleFonts.sourceCodePro(
                fontSize: 12,
                fontWeight: FontWeight.w700,
                color: valueColor,
              ),
            ),
          ),
        ],
      ),
    );
  }

  // ---------------------------------------------------------------------------
  // Painting Image & Procedural Stand-in Canvas System (Art Gallery Aesthetic)
  // ---------------------------------------------------------------------------

  Widget _buildPaintingImageWidget(String? imageUrl, String title, String artist) {
    if (imageUrl == null || imageUrl.trim().isEmpty) {
      return _buildProceduralStandInCanvas(title, artist);
    }
    final clean = imageUrl.trim();
    if (clean.startsWith("data:image")) {
      try {
        final b64 = clean.split(",").last;
        final bytes = base64Decode(b64);
        return Image.memory(
          bytes,
          fit: BoxFit.cover,
          errorBuilder: (_, __, ___) => _buildProceduralStandInCanvas(title, artist),
        );
      } catch (_) {
        return _buildProceduralStandInCanvas(title, artist);
      }
    }

    final fullUrl = clean.startsWith("http") ? clean : "${apiClient.baseUrl}$clean";
    return Image.network(
      fullUrl,
      fit: BoxFit.cover,
      errorBuilder: (_, __, ___) => _buildProceduralStandInCanvas(title, artist),
      loadingBuilder: (context, child, progress) {
        if (progress == null) return child;
        return _buildProceduralStandInCanvas(title, artist);
      },
    );
  }

  Widget _buildPaintingFrame(Map<String, dynamic> item) {
    final title = (item["artwork_title"] ?? "Untitled").toString();
    final artist = (item["artist_name"] ?? "Artist").toString();
    final imageUrl = item["image_url"]?.toString();
    final medium = (item["medium"] ?? "Oil on canvas").toString();
    final dimensions = (item["dimensions"] ?? "120 x 90 cm").toString();
    final year = item["year"]?.toString() ?? "2024";

    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF1E1E24), // Museum wall beveled frame border
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.18),
            blurRadius: 18,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      padding: const EdgeInsets.all(8), // Inner frame bezel
      child: Column(
        children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(10),
            child: AspectRatio(
              aspectRatio: 16 / 10,
              child: Stack(
                fit: StackFit.expand,
                children: [
                  // Real Image with fallback or Procedural Artistic Canvas
                  _buildPaintingImageWidget(imageUrl, title, artist),

                  // Subtle gallery spotlight gradient over the canvas
                  Container(
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        begin: Alignment.topCenter,
                        end: Alignment.bottomCenter,
                        colors: [
                          Colors.white.withValues(alpha: 0.12),
                          Colors.transparent,
                          Colors.black.withValues(alpha: 0.45),
                        ],
                      ),
                    ),
                  ),

                  // Exhibition Badge
                  Positioned(
                    top: 10,
                    left: 10,
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                      decoration: BoxDecoration(
                        color: Colors.black.withValues(alpha: 0.65),
                        borderRadius: BorderRadius.circular(20),
                        border: Border.all(color: Colors.white.withValues(alpha: 0.2)),
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          const Icon(Icons.verified_outlined, color: AppTheme.bubbleYellow, size: 13),
                          const SizedBox(width: 4),
                          Text(
                            "VERIFIED CANVAS",
                            style: GoogleFonts.inter(
                              fontSize: 10,
                              fontWeight: FontWeight.w700,
                              letterSpacing: 0.8,
                              color: Colors.white,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),

                  // Token ID badge
                  Positioned(
                    top: 10,
                    right: 10,
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                      decoration: BoxDecoration(
                        color: Colors.black.withValues(alpha: 0.65),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Text(
                        "#${item['token_id']}",
                        style: GoogleFonts.sourceCodePro(
                          fontSize: 11,
                          fontWeight: FontWeight.w700,
                          color: Colors.white,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),

          // Museum Brass Exhibition Plaque underneath painting
          Container(
            margin: const EdgeInsets.only(top: 8),
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
            decoration: BoxDecoration(
              gradient: const LinearGradient(
                colors: [Color(0xFF2D2D35), Color(0xFF222228)],
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
              ),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: const Color(0xFFD4AF37).withValues(alpha: 0.3), width: 0.8),
            ),
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        artist.toUpperCase(),
                        style: GoogleFonts.inter(
                          fontSize: 10.5,
                          fontWeight: FontWeight.w700,
                          letterSpacing: 1.2,
                          color: const Color(0xFFD4AF37), // Brass gold
                        ),
                      ),
                      Text(
                        title,
                        style: GoogleFonts.newsreader(
                          fontSize: 14,
                          fontWeight: FontWeight.w600,
                          fontStyle: FontStyle.italic,
                          color: Colors.white,
                        ),
                      ),
                      Text(
                        "$medium · $dimensions · $year",
                        style: GoogleFonts.inter(
                          fontSize: 10,
                          color: Colors.white.withValues(alpha: 0.65),
                        ),
                      ),
                    ],
                  ),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: Colors.white.withValues(alpha: 0.08),
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(Icons.nfc_rounded, color: Color(0xFFD4AF37), size: 14),
                      const SizedBox(width: 4),
                      Text(
                        "SUN Chip",
                        style: GoogleFonts.sourceCodePro(fontSize: 10, color: const Color(0xFFD4AF37), fontWeight: FontWeight.w600),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  /// Generates a rich, textured procedural fine-art stand-in canvas when no picture is uploaded
  Widget _buildProceduralStandInCanvas(String title, String artist) {
    // Generate distinct artistic color schemes based on artwork title
    List<Color> canvasColors;
    if (title.toLowerCase().contains("blue")) {
      canvasColors = const [Color(0xFF0F172A), Color(0xFF1E3A8A), Color(0xFF2563EB), Color(0xFF60A5FA)];
    } else if (title.toLowerCase().contains("relief") || title.toLowerCase().contains("chromatic")) {
      canvasColors = const [Color(0xFF7F1D1D), Color(0xFFC2410C), Color(0xFFD97706), Color(0xFFFEF08A)];
    } else if (title.toLowerCase().contains("nocturne") || title.toLowerCase().contains("gold")) {
      canvasColors = const [Color(0xFF18181B), Color(0xFF27272A), Color(0xFF78350F), Color(0xFFD97706)];
    } else {
      canvasColors = const [Color(0xFF1E293B), Color(0xFF334155), Color(0xFF475569), Color(0xFF94A3B8)];
    }

    return Container(
      decoration: BoxDecoration(
        gradient: RadialGradient(
          center: const Alignment(-0.2, -0.3),
          radius: 1.2,
          colors: canvasColors,
        ),
      ),
      child: Stack(
        children: [
          // Artistic impasto / canvas texture simulation
          Positioned.fill(
            child: Opacity(
              opacity: 0.15,
              child: CustomPaint(
                painter: _CanvasTexturePainter(),
              ),
            ),
          ),
          Center(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 24),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.palette_outlined, color: Colors.white.withValues(alpha: 0.6), size: 36),
                  const SizedBox(height: 8),
                  Text(
                    title,
                    textAlign: TextAlign.center,
                    style: GoogleFonts.newsreader(
                      fontSize: 18,
                      fontWeight: FontWeight.w700,
                      fontStyle: FontStyle.italic,
                      color: Colors.white,
                      letterSpacing: -0.3,
                      shadows: [
                        Shadow(color: Colors.black.withValues(alpha: 0.8), blurRadius: 10),
                      ],
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    "by $artist",
                    style: GoogleFonts.inter(
                      fontSize: 12,
                      fontWeight: FontWeight.w500,
                      color: Colors.white.withValues(alpha: 0.8),
                    ),
                  ),
                  const SizedBox(height: 10),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
                    decoration: BoxDecoration(
                      color: Colors.black.withValues(alpha: 0.4),
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: Colors.white.withValues(alpha: 0.2)),
                    ),
                    child: Text(
                      "Curated Oil on Canvas · Gallery Stand-in",
                      style: GoogleFonts.inter(fontSize: 10, color: Colors.white.withValues(alpha: 0.85)),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.bgLight,
      body: ArtisticBackground(
        child: SafeArea(
          bottom: false,
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const SizedBox(height: 16),
                // Header with Museum Gallery Styling
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          "Arthentic Gallery.",
                          style: GoogleFonts.newsreader(
                            fontSize: 34,
                            fontWeight: FontWeight.w600,
                            fontStyle: FontStyle.italic,
                            color: AppTheme.textPrimary,
                            letterSpacing: -0.5,
                          ),
                        ),
                        Text(
                          "Curated Fine Art Marketplace & Escrow Vault",
                          style: GoogleFonts.inter(fontSize: 12, color: AppTheme.textSecondary),
                        ),
                      ],
                    ),
                    ElevatedButton.icon(
                      onPressed: _showCreateListingModal,
                      icon: const Icon(Icons.add_rounded, size: 16),
                      label: Text("List Art", style: GoogleFonts.inter(fontSize: 12, fontWeight: FontWeight.w600)),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: AppTheme.brandDark,
                        foregroundColor: Colors.white,
                        elevation: 0,
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 14),

                // Base L2 DEX Swap Entry Card (Aerodrome / Uniswap v3)
                InkWell(
                  onTap: () => _showDexSwapModal(),
                  borderRadius: BorderRadius.circular(16),
                  child: Container(
                    padding: const EdgeInsets.all(14),
                    decoration: BoxDecoration(
                      gradient: const LinearGradient(
                        colors: [Color(0xFF0F172A), Color(0xFF1E293B)],
                        begin: Alignment.topLeft,
                        end: Alignment.bottomRight,
                      ),
                      borderRadius: BorderRadius.circular(16),
                      boxShadow: [
                        BoxShadow(
                          color: Colors.black.withValues(alpha: 0.1),
                          blurRadius: 10,
                          offset: const Offset(0, 4),
                        ),
                      ],
                    ),
                    child: Row(
                      children: [
                        Container(
                          padding: const EdgeInsets.all(10),
                          decoration: BoxDecoration(
                            color: const Color(0xFF3B82F6).withValues(alpha: 0.2),
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: const Icon(Icons.currency_exchange_rounded, color: Color(0xFF60A5FA), size: 22),
                        ),
                        const SizedBox(width: 14),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                children: [
                                  Text(
                                    "Base L2 DEX Swap (ETH ⇄ USDC)",
                                    style: GoogleFonts.inter(fontSize: 13.5, fontWeight: FontWeight.w700, color: Colors.white),
                                  ),
                                  const SizedBox(width: 6),
                                  Container(
                                    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                    decoration: BoxDecoration(
                                      color: const Color(0xFF10B981).withValues(alpha: 0.2),
                                      borderRadius: BorderRadius.circular(6),
                                    ),
                                    child: Text(
                                      "Aerodrome AMM",
                                      style: GoogleFonts.inter(fontSize: 9.5, fontWeight: FontWeight.w700, color: const Color(0xFF34D399)),
                                    ),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 2),
                              Text(
                                r"1 ETH = 3,000 USDC · 0.5% slippage · ~$0.01 gas · Instant liquidity",
                                style: GoogleFonts.sourceCodePro(fontSize: 11, color: Colors.white.withValues(alpha: 0.75)),
                              ),
                            ],
                          ),
                        ),
                        const Icon(Icons.arrow_forward_ios_rounded, color: Colors.white70, size: 14),
                      ],
                    ),
                  ),
                ),

                const SizedBox(height: 12),

                // A6 Hardware Sensor Tier Simulator Banner
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                  decoration: BoxDecoration(
                    color: _hasProLidarHardware ? const Color(0xFFECFDF5) : const Color(0xFFFEF3C7),
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(
                      color: _hasProLidarHardware ? const Color(0xFF10B981).withValues(alpha: 0.5) : const Color(0xFFF59E0B).withValues(alpha: 0.5),
                    ),
                  ),
                  child: Row(
                    children: [
                      Icon(
                        _hasProLidarHardware ? Icons.radar_rounded : Icons.phone_android_rounded,
                        color: _hasProLidarHardware ? const Color(0xFF059669) : const Color(0xFFB45309),
                        size: 22,
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              _hasProLidarHardware
                                  ? "A6 Hardware Tier: iPhone Pro LiDAR Active"
                                  : "A6 Hardware Tier: Standard NFC Phone (No LiDAR)",
                              style: GoogleFonts.inter(
                                fontSize: 12.5,
                                fontWeight: FontWeight.w700,
                                color: _hasProLidarHardware ? const Color(0xFF065F46) : const Color(0xFF92400E),
                              ),
                            ),
                            Text(
                              _hasProLidarHardware
                                  ? "Full L1 NFC + L2 8-Point Depth Scan unlocked for C-06 Escrow Release."
                                  : "L1 NFC Provenance allowed; C-06 Escrow Release gated until Pro LiDAR scan.",
                              style: GoogleFonts.inter(
                                fontSize: 11.5,
                                color: _hasProLidarHardware ? const Color(0xFF047857) : const Color(0xFFB45309),
                              ),
                            ),
                          ],
                        ),
                      ),
                      Switch(
                        value: _hasProLidarHardware,
                        activeThumbColor: const Color(0xFF059669),
                        onChanged: (val) => setState(() => _hasProLidarHardware = val),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 14),

                // Filter Pills
                SingleChildScrollView(
                  scrollDirection: Axis.horizontal,
                  child: Row(
                    children: [
                      _buildFilterChip("ALL", "All Gallery Works"),
                      const SizedBox(width: 8),
                      _buildFilterChip("USDC", "USDC (Permit2)"),
                      const SizedBox(width: 8),
                      _buildFilterChip("ETH", "Base ETH"),
                      const SizedBox(width: 8),
                      _buildFilterChip("ESCROW", "Active Escrows"),
                    ],
                  ),
                ),
                const SizedBox(height: 16),

                if (_isLoading)
                  const Padding(
                    padding: EdgeInsets.symmetric(vertical: 40),
                    child: Center(child: CircularProgressIndicator()),
                  )
                else
                  ..._filteredListings.map(_buildListingCard),

                const SizedBox(height: 40),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildFilterChip(String code, String label) {
    final isSelected = _selectedFilter == code;
    return GestureDetector(
      onTap: () => setState(() => _selectedFilter = code),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
        decoration: BoxDecoration(
          color: isSelected ? AppTheme.brandDark : Colors.white,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: isSelected ? AppTheme.brandDark : AppTheme.borderLight),
        ),
        child: Text(
          label,
          style: GoogleFonts.inter(
            fontSize: 12.5,
            fontWeight: isSelected ? FontWeight.w700 : FontWeight.w500,
            color: isSelected ? Colors.white : AppTheme.textSecondary,
          ),
        ),
      ),
    );
  }

  Widget _buildListingCard(Map<String, dynamic> item) {
    final status = (item["status"] ?? "ACTIVE").toString();
    final asset = (item["asset"] ?? "USDC").toString();
    final price = item["price_amount"] ?? 0.0;
    final split = item["split_breakdown"] as Map<String, dynamic>? ?? {};
    final escrow = item["active_escrow"] as Map<String, dynamic>?;
    final curationNotes = item["curation_notes"]?.toString();

    Color statusBg = const Color(0xFFDBEAFE);
    Color statusFg = const Color(0xFF1D4ED8);
    if (status == "ESCROW_LOCKED") {
      statusBg = const Color(0xFFFEF3C7);
      statusFg = const Color(0xFFB45309);
    } else if (status == "RELEASED") {
      statusBg = const Color(0xFFD1FAE5);
      statusFg = const Color(0xFF065F46);
    } else if (status == "DISPUTED") {
      statusBg = const Color(0xFFFEE2E2);
      statusFg = const Color(0xFF991B1B);
    } else if (status == "REFUNDED") {
      statusBg = const Color(0xFFEDE9FE);
      statusFg = const Color(0xFF5B21B6);
    }

    return Container(
      margin: const EdgeInsets.only(bottom: 24),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: AppTheme.borderLight),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.04),
            blurRadius: 14,
            offset: const Offset(0, 6),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // 1. Picture Frame with Real or Stand-In Painting Canvas
          _buildPaintingFrame(item),

          const SizedBox(height: 14),

          // 2. Status & Price Badges
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: statusBg,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(
                  status,
                  style: GoogleFonts.sourceCodePro(
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                    color: statusFg,
                  ),
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                decoration: BoxDecoration(
                  color: const Color(0xFFF8FAFC),
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: AppTheme.borderLight),
                ),
                child: Text(
                  "$price $asset",
                  style: GoogleFonts.sourceCodePro(
                    fontSize: 14,
                    fontWeight: FontWeight.w800,
                    color: AppTheme.textPrimary,
                  ),
                ),
              ),
            ],
          ),

          if (curationNotes != null && curationNotes.isNotEmpty) ...[
            const SizedBox(height: 10),
            Text(
              curationNotes,
              style: GoogleFonts.inter(
                fontSize: 12,
                color: AppTheme.textSecondary,
                height: 1.35,
                fontStyle: FontStyle.italic,
              ),
            ),
          ],

          const SizedBox(height: 12),

          // 3. A5 3-Way Split Bar
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: const Color(0xFFF8FAFC),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: AppTheme.borderLight),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  "On-Chain 3-Way Payout Split (A5: ArthenticEscrow.sol)",
                  style: GoogleFonts.inter(fontSize: 11.5, fontWeight: FontWeight.w700, color: AppTheme.textPrimary),
                ),
                const SizedBox(height: 6),
                _buildSplitRow("93.5% Seller Payout", "${split['seller_payout_amount']} $asset", const Color(0xFF065F46)),
                _buildSplitRow("5.0% Artist Royalty (ERC-2981)", "${split['artist_royalty_amount']} $asset", AppTheme.brandBlue),
                _buildSplitRow("1.5% Platform Treasury Safe", "${split['platform_fee_amount']} $asset", const Color(0xFF92400E)),
              ],
            ),
          ),

          const SizedBox(height: 14),

          // 4. Action Buttons (Buy via Escrow or Swap & Buy)
          if (status == "ACTIVE") ...[
            Row(
              children: [
                Expanded(
                  child: ElevatedButton.icon(
                    onPressed: () => _showDepositEscrowSheet(item),
                    icon: const Icon(Icons.account_balance_wallet_outlined, size: 18),
                    label: Text(
                      "Buy via Escrow ($price $asset)",
                      style: GoogleFonts.inter(fontWeight: FontWeight.w600, fontSize: 13),
                    ),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: AppTheme.brandDark,
                      foregroundColor: Colors.white,
                      elevation: 0,
                      padding: const EdgeInsets.symmetric(vertical: 13),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                IconButton.filledTonal(
                  onPressed: () => _showDexSwapModal(
                    initialFrom: asset == "USDC" ? "ETH" : "USDC",
                    initialTo: asset,
                    initialAmount: asset == "USDC" ? (price / 3000.0) : (price * 3000.0),
                  ),
                  icon: const Icon(Icons.swap_horiz_rounded, size: 20),
                  tooltip: "Swap on Base L2 DEX",
                ),
              ],
            ),
          ] else if (escrow != null) ...[
            _buildEscrowLifecyclePanel(item, escrow),
          ],
        ],
      ),
    );
  }

  Widget _buildEscrowLifecyclePanel(Map<String, dynamic> listing, Map<String, dynamic> escrow) {
    final escId = escrow["id"].toString();
    final escStatus = escrow["status"].toString();
    final l1Done = _l1TappedEscrows.contains(escId) || escrow["l1_nfc_verified"] == true;
    final l2Done = _l2ScannedEscrows.contains(escId) || escrow["l2_lidar_verified"] == true;

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFFFFFBEB),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFFF59E0B).withValues(alpha: 0.5)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                "Physical-Delivery Escrow Vault (SD-04)",
                style: GoogleFonts.inter(fontSize: 13, fontWeight: FontWeight.w700, color: const Color(0xFF92400E)),
              ),
              Text(
                escStatus,
                style: GoogleFonts.sourceCodePro(fontSize: 11, fontWeight: FontWeight.w700, color: const Color(0xFFB45309)),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            "Escrow Contract (${ArthenticContractConfig.baseSepoliaNetworkName}): ${ArthenticContractConfig.shortAddress(ArthenticContractConfig.arthenticEscrowAddress)}",
            style: GoogleFonts.sourceCodePro(fontSize: 10.5, fontWeight: FontWeight.w600, color: const Color(0xFF92400E)),
          ),
          const SizedBox(height: 2),
          Text(
            "Deposit Tx: ${(escrow['deposit_tx_hash'] ?? '').toString().substring(0, 18)}...",
            style: GoogleFonts.sourceCodePro(fontSize: 11, color: AppTheme.textSecondary),
          ),
          if (escrow["permit2_signature"] != null) ...[
            const SizedBox(height: 2),
            Text(
              "USDC Permit2 Sig: ${(escrow['permit2_signature']).toString().substring(0, 22)}...",
              style: GoogleFonts.sourceCodePro(fontSize: 11, color: AppTheme.brandBlue),
            ),
          ],
          const SizedBox(height: 10),

          if (escStatus == "LOCKED") ...[
            // Step 1 & Step 2 Physical Verification Buttons
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: () {
                      setState(() => _l1TappedEscrows.add(escId));
                      walletService.recordSignature("[NFC L1] Verified NTAG 424 DNA chip for Escrow ${escId.substring(0, 6)}");
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(
                          backgroundColor: AppTheme.brandDark,
                          content: Text("Step 1 Passed: Physical NTAG 424 DNA SUN chip verified!"),
                        ),
                      );
                    },
                    icon: Icon(
                      l1Done ? Icons.check_circle_rounded : Icons.nfc_rounded,
                      size: 16,
                      color: l1Done ? const Color(0xFF059669) : AppTheme.brandBlue,
                    ),
                    label: Text(
                      l1Done ? "1. L1 NFC Valid" : "1. Tap L1 NFC",
                      style: GoogleFonts.inter(fontSize: 11.5, fontWeight: FontWeight.w600),
                    ),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: l1Done ? const Color(0xFF065F46) : AppTheme.brandBlue,
                      side: BorderSide(color: l1Done ? const Color(0xFF10B981) : AppTheme.brandBlue),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: () {
                      if (!_hasProLidarHardware) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          SnackBar(
                            backgroundColor: Colors.red.shade800,
                            content: const Text(
                              "A6 Hardware Tier Gate: Standard phone detected. Switch to iPhone Pro LiDAR above to run L2 surface scan.",
                            ),
                          ),
                        );
                        return;
                      }
                      setState(() => _l2ScannedEscrows.add(escId));
                      walletService.recordSignature("[LiDAR L2] 8-Point Surface Match 94.2% for Escrow ${escId.substring(0, 6)}");
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(
                          backgroundColor: AppTheme.brandDark,
                          content: Text("Step 2 Passed: 8-Point Pro LiDAR Surface Scan matched 94.2% (>= 85%)!"),
                        ),
                      );
                    },
                    icon: Icon(
                      l2Done ? Icons.check_circle_rounded : Icons.radar_rounded,
                      size: 16,
                      color: l2Done ? const Color(0xFF059669) : const Color(0xFF7C3AED),
                    ),
                    label: Text(
                      l2Done ? "2. L2 94.2% OK" : "2. Scan L2 LiDAR",
                      style: GoogleFonts.inter(fontSize: 11.5, fontWeight: FontWeight.w600),
                    ),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: l2Done ? const Color(0xFF065F46) : const Color(0xFF7C3AED),
                      side: BorderSide(color: l2Done ? const Color(0xFF10B981) : const Color(0xFF7C3AED)),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            // Step 3: Release Escrow (C-06) or Open Dispute (C-10)
            Row(
              children: [
                Expanded(
                  flex: 2,
                  child: ElevatedButton.icon(
                    onPressed: () async {
                      final res = await apiClient.confirmPhysicalDelivery(
                        escrowId: escId,
                        buyerWallet: walletService.address,
                        l1NfcVerified: l1Done,
                        hasProLidar: _hasProLidarHardware,
                        l2SimilarityScore: 0.942,
                      );
                      if (mounted) {
                        if (res["success"] == true) {
                          walletService.recordSignature(
                            "[MetaMask C-06] Confirmed delivery & released 93.5% Seller / 5% Artist / 1.5% Treasury!",
                          );
                          _loadListings();
                          ScaffoldMessenger.of(context).showSnackBar(
                            const SnackBar(
                              backgroundColor: Color(0xFF065F46),
                              content: Text("C-06 Delivery Confirmed! NFT transferred & 3-way payout released on Base L2."),
                            ),
                          );
                        } else {
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(
                              backgroundColor: Colors.red.shade800,
                              content: Text(res["error"]?.toString() ?? "Delivery confirmation blocked"),
                            ),
                          );
                        }
                      }
                    },
                    icon: const Icon(Icons.verified_user_rounded, size: 16),
                    label: Text(
                      "Confirm & Release (C-06)",
                      style: GoogleFonts.inter(fontSize: 12, fontWeight: FontWeight.w700),
                    ),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF059669),
                      foregroundColor: Colors.white,
                      elevation: 0,
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  flex: 1,
                  child: OutlinedButton(
                    onPressed: () async {
                      await apiClient.disputeEscrow(
                        escrowId: escId,
                        callerWallet: walletService.address,
                        reason: "L2 LiDAR surface anomaly (< 0.85 similarity) detected upon unpacking.",
                      );
                      walletService.recordSignature("[MetaMask C-10] Opened Escrow Dispute for ${escId.substring(0, 6)}");
                      if (mounted) {
                        _loadListings();
                        ScaffoldMessenger.of(context).showSnackBar(
                          SnackBar(
                            backgroundColor: Colors.red.shade800,
                            content: const Text("C-10 Dispute opened! Escrow frozen for Arbitrator Council review."),
                          ),
                        );
                      }
                    },
                    style: OutlinedButton.styleFrom(
                      foregroundColor: Colors.red.shade700,
                      side: BorderSide(color: Colors.red.shade300),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                    ),
                    child: Text("Dispute (C-10)", style: GoogleFonts.inter(fontSize: 11.5, fontWeight: FontWeight.w600)),
                  ),
                ),
              ],
            ),
          ] else if (escStatus == "DISPUTED") ...[
            Text(
              "Dispute Reason: ${escrow['dispute_reason'] ?? 'L2 Surface mismatch'}",
              style: GoogleFonts.inter(fontSize: 12, color: const Color(0xFF991B1B), fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(
                  child: ElevatedButton(
                    onPressed: () async {
                      await apiClient.resolveEscrow(escrowId: escId, action: "refund_buyer");
                      if (mounted) _loadListings();
                    },
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF5B21B6),
                      foregroundColor: Colors.white,
                      elevation: 0,
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                    ),
                    child: Text("Arbitrator: Refund Buyer (C-11)", style: GoogleFonts.inter(fontSize: 11.5, fontWeight: FontWeight.w600)),
                  ),
                ),
              ],
            ),
          ] else if (escStatus == "DELIVERY_VERIFIED_RELEASED") ...[
            Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: const Color(0xFFD1FAE5),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Row(
                children: [
                  const Icon(Icons.check_circle_rounded, color: Color(0xFF059669), size: 18),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      "Settled Atomic 3-Way Split: ${escrow['seller_payout_amount']} ${escrow['asset']} Seller · ${escrow['artist_royalty_amount']} ${escrow['asset']} Artist · ${escrow['platform_fee_amount']} ${escrow['asset']} Treasury",
                      style: GoogleFonts.inter(fontSize: 11.5, fontWeight: FontWeight.w600, color: const Color(0xFF065F46)),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }
}

/// Custom painter for textured linen weave canvas effect on procedural stand-in art
class _CanvasTexturePainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = Colors.white.withValues(alpha: 0.1)
      ..strokeWidth = 0.8;

    // Draw cross-hatch canvas weave
    const step = 8.0;
    for (double x = 0; x < size.width; x += step) {
      canvas.drawLine(Offset(x, 0), Offset(x, size.height), paint);
    }
    for (double y = 0; y < size.height; y += step) {
      canvas.drawLine(Offset(0, y), Offset(size.width, y), paint);
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
