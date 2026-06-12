import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:webview_flutter_platform_interface/webview_flutter_platform_interface.dart';
import 'package:prosartisan_mobile/main.dart';

// Fakes pour éviter les dépendances de plateforme natives en mode test widget
class FakeWebViewPlatform extends WebViewPlatform {
  @override
  PlatformWebViewController createPlatformWebViewController(
    PlatformWebViewControllerCreationParams params,
  ) {
    return FakeWebViewController(params);
  }

  @override
  PlatformNavigationDelegate createPlatformNavigationDelegate(
    PlatformNavigationDelegateCreationParams params,
  ) {
    return FakeNavigationDelegate(params);
  }

  @override
  PlatformWebViewWidget createPlatformWebViewWidget(
    PlatformWebViewWidgetCreationParams params,
  ) {
    return FakeWebViewWidget(params);
  }

  @override
  PlatformWebViewCookieManager createPlatformCookieManager(
    PlatformWebViewCookieManagerCreationParams params,
  ) {
    return FakeWebViewCookieManager(params);
  }
}

class FakeWebViewController extends PlatformWebViewController {
  FakeWebViewController(super.params) : super.implementation();

  @override
  Future<void> setJavaScriptMode(JavaScriptMode javaScriptMode) async {}

  @override
  Future<void> setBackgroundColor(Color color) async {}

  @override
  Future<void> setPlatformNavigationDelegate(PlatformNavigationDelegate delegate) async {}

  @override
  Future<void> loadFlutterAsset(String key) async {}
}

class FakeNavigationDelegate extends PlatformNavigationDelegate {
  FakeNavigationDelegate(super.params) : super.implementation();

  @override
  Future<void> setOnPageStarted(void Function(String url) onPageStarted) async {}

  @override
  Future<void> setOnPageFinished(void Function(String url) onPageFinished) async {}

  @override
  Future<void> setOnWebResourceError(void Function(WebResourceError error) onWebResourceError) async {}
}

class FakeWebViewWidget extends PlatformWebViewWidget {
  FakeWebViewWidget(super.params) : super.implementation();

  @override
  Widget build(BuildContext context) {
    return const SizedBox.shrink();
  }
}

class FakeWebViewCookieManager extends PlatformWebViewCookieManager {
  FakeWebViewCookieManager(super.params) : super.implementation();
}

void main() {
  setUpAll(() {
    // Enregistrer la fausse plateforme avant de lancer les tests
    WebViewPlatform.instance = FakeWebViewPlatform();
  });

  testWidgets('WebView App smoke test', (WidgetTester tester) async {
    // Build our app and trigger a frame.
    await tester.pumpWidget(const ProsArtisanMobileApp());

    // Vérifier que le Scaffold et l'application se chargent
    expect(find.byType(ProsArtisanMobileApp), findsOneWidget);
  });
}
