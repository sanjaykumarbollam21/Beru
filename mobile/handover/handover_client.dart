/// Mobile Session Handover Client for Beru.
/// Handles handover_request notifications, acceptance, and context resumption.

typedef SendWsJson = void Function(Map<String, dynamic> json);

class MobileHandoverClient {
  final SendWsJson sendWsMessage;
  final String deviceId;

  MobileHandoverClient({
    required this.sendWsMessage,
    required this.deviceId,
  });

  /// Handle incoming handover_request from Hub
  void handleHandoverRequest(Map<String, dynamic> data) {
    final handoverId = data["handover_id"];
    final summary = data["summary"] ?? "Continue session on phone";
    final contextType = data["context_type"] ?? "conversation";

    print("[Handover] Request received: $summary ($contextType)");
    // In production: shows heads-up notification with 'Accept' and 'Decline' actions
  }

  /// User accepts handover (by tapping notification or saying 'yes')
  void acceptHandover(String handoverId) {
    sendWsMessage({
      "type": "handover_accept",
      "handover_id": handoverId,
    });
  }

  /// Handle incoming state transfer upon acceptance
  void handleHandoverState(Map<String, dynamic> data) {
    final contextType = data["context_type"];
    final state = data["state"] as Map<String, dynamic>? ?? {};

    print("[Handover] Resuming task: $contextType with state: $state");

    if (contextType == "link") {
      final url = state["url"] as String?;
      if (url != null) {
        // In production: launchUrl(Uri.parse(url))
        print("Opening link in mobile browser: $url");
      }
    } else if (contextType == "conversation") {
      print("Restored chat turns: ${state['turns']?.length ?? 0}");
    }
  }
}
