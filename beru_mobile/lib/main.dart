import 'dart:async';
import 'dart:convert';
import 'dart:math';
import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;
import 'package:qr_flutter/qr_flutter.dart';
import 'package:uuid/uuid.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const BeruApp());
}

class BeruApp extends StatelessWidget {
  const BeruApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Beru Assistant',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF6366F1),
          brightness: Brightness.dark,
        ),
        useMaterial3: true,
      ),
      home: const BeruHomePage(),
    );
  }
}

class BeruHomePage extends StatefulWidget {
  const BeruHomePage({super.key});

  @override
  State<BeruHomePage> createState() => _BeruHomePageState();
}

class _BeruHomePageState extends State<BeruHomePage> {
  static const _storage = FlutterSecureStorage(
    aOptions: AndroidOptions(encryptedSharedPreferences: true),
  );

  // Connection & Config (empty by default, loaded from secure storage)
  String _hubUrl = '';
  String _deviceToken = '';
  String _deviceId = '';
  String _connectionStatus = 'offline'; // connected, reconnecting, offline
  bool _isLoading = false;

  // Pairing & Devices
  String _pairingCode = '';
  List<Map<String, dynamic>> _onlineDevices = [];
  String _commandStatus = ''; // delivered, ok, offline, unsupported, timeout
  String? _pendingCommandId;
  Timer? _commandTimeoutTimer;

  // WebSockets
  WebSocketChannel? _channel;
  bool _shouldReconnect = false;
  int _reconnectAttempts = 0;
  Timer? _reconnectTimer;

  // Controllers
  final _hubUrlController = TextEditingController();
  final _pairCodeController = TextEditingController();

  @override
  void initState() {
    super.initState();
    _loadStoredCredentials();
  }

  @override
  void dispose() {
    _shouldReconnect = false;
    _reconnectTimer?.cancel();
    _commandTimeoutTimer?.cancel();
    _channel?.sink.close();
    _hubUrlController.dispose();
    _pairCodeController.dispose();
    super.dispose();
  }

  Future<void> _loadStoredCredentials() async {
    final savedUrl = await _storage.read(key: 'hub_url');
    final savedToken = await _storage.read(key: 'device_token');
    final savedId = await _storage.read(key: 'device_id');

    setState(() {
      if (savedUrl != null && savedUrl.isNotEmpty) {
        _hubUrl = savedUrl;
      }
      _hubUrlController.text = _hubUrl;
      if (savedToken != null && savedToken.isNotEmpty) {
        _deviceToken = savedToken;
        _deviceId = savedId ?? '';
      }
    });

    if (_deviceToken.isNotEmpty) {
      _shouldReconnect = true;
      _connectWebSocket();
    }
  }

  Future<void> _saveHubUrl(String url) async {
    final cleanUrl = url.trim().replaceAll(RegExp(r'/+$'), '');
    await _storage.write(key: 'hub_url', value: cleanUrl);
    setState(() {
      _hubUrl = cleanUrl;
    });
    if (_deviceToken.isNotEmpty) {
      _disconnectWebSocket();
      _connectWebSocket();
    }
  }

  // --- Auth: Register & Pairing ---

  Future<void> _registerAsFirstDevice() async {
    setState(() => _isLoading = true);
    try {
      final res = await http.post(
        Uri.parse('$_hubUrl/register-first-device'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'device_name': 'Pixel Phone',
          'platform': 'android',
          'capabilities': ['ping', 'notify'],
        }),
      );

      if (res.statusCode == 200) {
        final data = jsonDecode(res.body);
        final token = data['token'] as String;
        final devId = data['device_id'] as String;

        await _storage.write(key: 'device_token', value: token);
        await _storage.write(key: 'device_id', value: devId);

        setState(() {
          _deviceToken = token;
          _deviceId = devId;
        });

        _showSnack('Registered successfully as first device');
        _shouldReconnect = true;
        _connectWebSocket();
      } else {
        _showSnack('Registration failed: ${res.body}');
      }
    } catch (e) {
      _showSnack('Error connecting to hub: $e');
    } finally {
      setState(() => _isLoading = false);
    }
  }

  Future<void> _generatePairingCode() async {
    if (_deviceToken.isEmpty) return;
    setState(() => _isLoading = true);
    try {
      final res = await http.post(
        Uri.parse('$_hubUrl/pair/start'),
        headers: {
          'Authorization': 'Bearer $_deviceToken',
          'Content-Type': 'application/json',
        },
      );

      if (res.statusCode == 200) {
        final data = jsonDecode(res.body);
        setState(() {
          _pairingCode = data['code'] as String;
        });
      } else {
        _showSnack('Failed to generate pairing code: ${res.body}');
      }
    } catch (e) {
      _showSnack('Error generating pairing code: $e');
    } finally {
      setState(() => _isLoading = false);
    }
  }

  Future<void> _completePairingWithCode() async {
    final code = _pairCodeController.text.trim();
    if (code.isEmpty) return;
    setState(() => _isLoading = true);
    try {
      final res = await http.post(
        Uri.parse('$_hubUrl/pair/complete'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'code': code,
          'device_name': 'Pixel Phone',
          'platform': 'android',
          'capabilities': ['ping', 'notify'],
        }),
      );

      if (res.statusCode == 200) {
        final data = jsonDecode(res.body);
        final token = data['token'] as String;
        final devId = data['device_id'] as String;

        await _storage.write(key: 'device_token', value: token);
        await _storage.write(key: 'device_id', value: devId);

        setState(() {
          _deviceToken = token;
          _deviceId = devId;
          _pairCodeController.clear();
        });

        _showSnack('Paired successfully with hub');
        _shouldReconnect = true;
        _connectWebSocket();
      } else {
        _showSnack('Pairing failed: ${res.body}');
      }
    } catch (e) {
      _showSnack('Error completing pairing: $e');
    } finally {
      setState(() => _isLoading = false);
    }
  }

  // --- WebSocket & Ticket Flow ---

  Future<void> _connectWebSocket() async {
    if (_deviceToken.isEmpty) return;

    _reconnectTimer?.cancel();
    setState(() {
      _connectionStatus = _reconnectAttempts > 0 ? 'reconnecting' : 'connecting';
    });

    try {
      // 1. Obtain single-use ticket
      final ticketRes = await http.post(
        Uri.parse('$_hubUrl/auth/ticket'),
        headers: {
          'Authorization': 'Bearer $_deviceToken',
          'Content-Type': 'application/json',
        },
      );

      if (ticketRes.statusCode != 200) {
        throw Exception('Failed to obtain ticket: ${ticketRes.body}');
      }

      final ticket = jsonDecode(ticketRes.body)['ticket'] as String;

      // 2. Open WebSocket with ?ticket=...
      final wsUrl = _hubUrl
          .replaceFirst(RegExp(r'^http'), 'ws')
          .replaceFirst(RegExp(r'^https'), 'wss');
      final uri = Uri.parse('$wsUrl/ws?ticket=$ticket&protocol_version=2.0');

      _channel = WebSocketChannel.connect(uri);

      _channel!.stream.listen(
        (data) {
          _reconnectAttempts = 0;
          if (_connectionStatus != 'connected') {
            setState(() => _connectionStatus = 'connected');
          }
          _handleWsMessage(data);
        },
        onError: (err) {
          _handleWsDisconnect();
        },
        onDone: () {
          _handleWsDisconnect();
        },
      );
    } catch (e) {
      _handleWsDisconnect();
    }
  }

  void _handleWsDisconnect() {
    setState(() {
      _connectionStatus = _shouldReconnect ? 'reconnecting' : 'offline';
    });

    if (_shouldReconnect) {
      _reconnectAttempts++;
      final baseSeconds = (_reconnectAttempts < 5) ? (1 << _reconnectAttempts) : 16;
      final jitterMs = Random().nextInt(1000);
      _reconnectTimer = Timer(Duration(seconds: baseSeconds, milliseconds: jitterMs), () {
        if (_shouldReconnect) {
          _connectWebSocket();
        }
      });
    }
  }

  void _disconnectWebSocket() {
    _shouldReconnect = false;
    _reconnectTimer?.cancel();
    _channel?.sink.close();
    setState(() => _connectionStatus = 'offline');
  }

  void _handleWsMessage(dynamic raw) {
    try {
      final msg = jsonDecode(raw.toString()) as Map<String, dynamic>;
      final type = msg['type'] as String?;

      if (type == 'devices') {
        final list = (msg['online'] as List? ?? [])
            .map((e) => Map<String, dynamic>.from(e as Map))
            .toList();
        setState(() {
          _onlineDevices = list;
        });
      } else if (type == 'command_status') {
        final cmdId = msg['command_id'] as String?;
        final status = msg['status'] as String? ?? 'unknown';

        if (cmdId == _pendingCommandId) {
          _commandTimeoutTimer?.cancel();
          setState(() {
            _commandStatus = status;
          });
        }
      } else if (type == 'execute') {
        _handleExecuteCommand(msg);
      }
    } catch (_) {}
  }

  void _handleExecuteCommand(Map<String, dynamic> msg) {
    final cmdId = msg['command_id'] as String;
    final action = msg['action'] as String;

    if (action == 'ping') {
      setState(() {
        _commandStatus = 'received ping';
      });
      _channel?.sink.add(jsonEncode({
        'type': 'result',
        'command_id': cmdId,
        'status': 'ok',
        'result': {'pong': true, 'device': 'android'},
      }));
      _showSnack('Received ping from hub/PC');
    } else if (action == 'notify') {
      setState(() {
        _commandStatus = 'received notify';
      });
      final text = (msg['params'] as Map?)?['message'] ?? 'Notification from Beru';
      _showSnack(text.toString());
      _channel?.sink.add(jsonEncode({
        'type': 'result',
        'command_id': cmdId,
        'status': 'ok',
        'result': {'notified': true},
      }));
    } else {
      // Screen lock on standard Android is unsupported without Device Admin
      _channel?.sink.add(jsonEncode({
        'type': 'result',
        'command_id': cmdId,
        'status': 'error',
        'error': 'unsupported',
      }));
    }
  }

  // --- Send Command ---

  void _sendCommandToDevice(String target, String action) {
    if (_channel == null || _connectionStatus != 'connected') {
      _showSnack('Not connected to hub');
      return;
    }

    final cmdId = const Uuid().v4();
    _pendingCommandId = cmdId;
    setState(() {
      _commandStatus = 'sending...';
    });

    _commandTimeoutTimer?.cancel();
    _commandTimeoutTimer = Timer(const Duration(seconds: 10), () {
      if (_pendingCommandId == cmdId && _commandStatus == 'sending...') {
        setState(() {
          _commandStatus = 'timeout';
        });
      }
    });

    _channel?.sink.add(jsonEncode({
      'type': 'command',
      'id': cmdId,
      'target': target,
      'action': action,
      'params': {},
    }));
  }

  void _showSnack(String msg) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(msg), duration: const Duration(seconds: 3)),
    );
  }

  Color _getStatusColor() {
    switch (_connectionStatus) {
      case 'connected':
        return Colors.greenAccent;
      case 'reconnecting':
        return Colors.orangeAccent;
      default:
        return Colors.redAccent;
    }
  }

  @override
  Widget build(BuildContext context) {
    final otherDevices = _onlineDevices.where((d) => d['id'] != _deviceId).toList();

    return Scaffold(
      appBar: AppBar(
        title: const Text('Beru Assistant (Phase 1)'),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 16.0),
            child: Chip(
              avatar: CircleAvatar(
                backgroundColor: _getStatusColor(),
                radius: 5,
              ),
              label: Text(_connectionStatus.toUpperCase()),
            ),
          ),
        ],
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(16.0),
              children: [
                // 1. Hub Settings Card
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(16.0),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('Hub Connection Settings',
                            style: Theme.of(context).textTheme.titleMedium),
                        const SizedBox(height: 8),
                        Row(
                          children: [
                            Expanded(
                              child: TextField(
                                controller: _hubUrlController,
                                decoration: const InputDecoration(
                                  labelText: 'Hub Base URL (e.g. http://192.168.1.50:8000)',
                                  border: OutlineInputBorder(),
                                  isDense: true,
                                ),
                              ),
                            ),
                            const SizedBox(width: 8),
                            ElevatedButton(
                              onPressed: () => _saveHubUrl(_hubUrlController.text),
                              child: const Text('Save'),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 12),

                // 2. Registration & Pairing Card
                if (_deviceToken.isEmpty) ...[
                  Card(
                    color: Colors.indigo.shade900.withAlpha(80),
                    child: Padding(
                      padding: const EdgeInsets.all(16.0),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('Device Registration / Pairing',
                              style: Theme.of(context).textTheme.titleMedium),
                          const SizedBox(height: 12),
                          Row(
                            children: [
                              Expanded(
                                child: ElevatedButton.icon(
                                  icon: const Icon(Icons.star),
                                  label: const Text('Register as First Device'),
                                  onPressed: _registerAsFirstDevice,
                                ),
                              ),
                            ],
                          ),
                          const Divider(height: 24),
                          Text('Or Pair with Existing Code:',
                              style: Theme.of(context).textTheme.bodySmall),
                          const SizedBox(height: 8),
                          Row(
                            children: [
                              Expanded(
                                child: TextField(
                                  controller: _pairCodeController,
                                  textCapitalization: TextCapitalization.characters,
                                  decoration: const InputDecoration(
                                    labelText: 'Enter 6-char pairing code',
                                    border: OutlineInputBorder(),
                                    isDense: true,
                                  ),
                                ),
                              ),
                              const SizedBox(width: 8),
                              ElevatedButton(
                                onPressed: _completePairingWithCode,
                                child: const Text('Pair'),
                              ),
                            ],
                          ),
                        ],
                      ),
                    ),
                  ),
                ] else ...[
                  // Registered State: Generate Code
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(16.0),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              Text('Pair Another Device',
                                  style: Theme.of(context).textTheme.titleMedium),
                              ElevatedButton.icon(
                                icon: const Icon(Icons.qr_code),
                                label: const Text('Get Code'),
                                onPressed: _generatePairingCode,
                              ),
                            ],
                          ),
                          if (_pairingCode.isNotEmpty) ...[
                            const SizedBox(height: 16),
                            Center(
                              child: Column(
                                children: [
                                  QrImageView(
                                    data: _pairingCode,
                                    version: QrVersions.auto,
                                    size: 140.0,
                                    backgroundColor: Colors.white,
                                  ),
                                  const SizedBox(height: 8),
                                  SelectableText(
                                    _pairingCode,
                                    style: Theme.of(context)
                                        .textTheme
                                        .headlineMedium
                                        ?.copyWith(
                                          letterSpacing: 4,
                                          fontWeight: FontWeight.bold,
                                        ),
                                  ),
                                  const Text('Valid for 60 seconds',
                                      style: TextStyle(color: Colors.grey)),
                                ],
                              ),
                            ),
                          ],
                        ],
                      ),
                    ),
                  ),
                ],
                const SizedBox(height: 12),

                // 3. Online Devices & Lock Test Card
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(16.0),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Text('Live Online Devices (${_onlineDevices.length})',
                                style: Theme.of(context).textTheme.titleMedium),
                            if (_commandStatus.isNotEmpty)
                              Chip(
                                label: Text('Status: $_commandStatus'),
                                backgroundColor: _commandStatus == 'ok'
                                    ? Colors.green.shade900
                                    : Colors.blueGrey.shade900,
                              ),
                          ],
                        ),
                        const SizedBox(height: 8),
                        if (_onlineDevices.isEmpty)
                          const Padding(
                            padding: EdgeInsets.symmetric(vertical: 16.0),
                            child: Text('No devices online yet.',
                                style: TextStyle(color: Colors.grey)),
                          ),
                        for (final dev in _onlineDevices)
                          ListTile(
                            leading: Icon(
                              dev['platform'] == 'windows'
                                  ? Icons.laptop_windows
                                  : Icons.phone_android,
                              color: dev['id'] == _deviceId
                                  ? Colors.indigoAccent
                                  : Colors.greenAccent,
                            ),
                            title: Text(
                              '${dev['name']}${dev['id'] == _deviceId ? ' (This Phone)' : ''}',
                              style: const TextStyle(fontWeight: FontWeight.w600),
                            ),
                            subtitle: Text('ID: ${dev['id']}\nPlatform: ${dev['platform']}'),
                            isThreeLine: true,
                          ),
                        const Divider(height: 24),
                        Text('Cross-Device Test Actions:',
                            style: Theme.of(context).textTheme.titleSmall),
                        const SizedBox(height: 8),
                        if (otherDevices.isEmpty)
                          const Text('Connect your PC to test cross-device lock.',
                              style: TextStyle(color: Colors.grey))
                        else
                          for (final other in otherDevices) ...[
                            Row(
                              children: [
                                Expanded(
                                  child: ElevatedButton.icon(
                                    icon: const Icon(Icons.lock),
                                    label: Text('Send Lock to ${other['name']}'),
                                    style: ElevatedButton.styleFrom(
                                      backgroundColor: Colors.amber.shade900,
                                      foregroundColor: Colors.white,
                                    ),
                                    onPressed: () => _sendCommandToDevice(
                                        other['id'] as String, 'lock'),
                                  ),
                                ),
                                const SizedBox(width: 8),
                                ElevatedButton.icon(
                                  icon: const Icon(Icons.network_ping),
                                  label: const Text('Ping'),
                                  onPressed: () => _sendCommandToDevice(
                                      other['id'] as String, 'ping'),
                                ),
                              ],
                            ),
                            const SizedBox(height: 8),
                          ],
                      ],
                    ),
                  ),
                ),
              ],
            ),
    );
  }
}
