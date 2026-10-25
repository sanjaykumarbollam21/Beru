import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

class PersonalizationScreen extends StatefulWidget {
  final String hubBaseUrl;
  final String deviceToken;

  const PersonalizationScreen({
    Key? key,
    required this.hubBaseUrl,
    required this.deviceToken,
  }) : super(key: key);

  @override
  _PersonalizationScreenState createState() => _PersonalizationScreenState();
}

class _PersonalizationScreenState extends State<PersonalizationScreen> {
  bool _isLoading = true;
  bool _learningEnabled = true;
  List<Map<String, dynamic>> _preferences = [];
  List<Map<String, dynamic>> _facts = [];
  List<Map<String, dynamic>> _routines = [];

  @override
  void initState() {
    super.initState();
    _loadData();
  }

  Map<String, String> get _headers => {
    'Authorization': 'Bearer ${widget.deviceToken}',
    'Content-Type': 'application/json',
  };

  Future<void> _loadData() async {
    setState(() => _isLoading = true);
    try {
      final res = await http.get(
        Uri.parse('${widget.hubBaseUrl}/personalization'),
        headers: _headers,
      );
      if (res.statusCode == 200) {
        final data = jsonDecode(res.body);
        setState(() {
          _preferences = List<Map<String, dynamic>>.from(data['preferences'] ?? []);
          _facts = List<Map<String, dynamic>>.from(data['facts'] ?? []);
          _routines = List<Map<String, dynamic>>.from(data['routines'] ?? []);
          
          final learnPref = _preferences.firstWhere(
            (p) => p['key'] == 'learning_enabled',
            orElse: () => {'value': true},
          );
          _learningEnabled = learnPref['value'] == true;
          _isLoading = false;
        });
      }
    } catch (e) {
      setState(() => _isLoading = false);
    }
  }

  Future<void> _toggleLearning(bool val) async {
    setState(() => _learningEnabled = val);
    await http.put(
      Uri.parse('${widget.hubBaseUrl}/personalization/preferences/learning_enabled'),
      headers: _headers,
      body: jsonEncode({'value': val}),
    );
  }

  Future<void> _deleteFact(String factId) async {
    await http.delete(
      Uri.parse('${widget.hubBaseUrl}/personalization/facts/$factId'),
      headers: _headers,
    );
    _loadData();
  }

  Future<void> _deleteRoutine(String name) async {
    await http.delete(
      Uri.parse('${widget.hubBaseUrl}/personalization/routines/$name'),
      headers: _headers,
    );
    _loadData();
  }

  Future<void> _resetAll() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Reset All Personalization?'),
        content: const Text('This will delete all preferences, remembered facts, and routines.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          TextButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Reset', style: TextStyle(color: Colors.red))),
        ],
      ),
    );

    if (confirmed == true) {
      await http.delete(
        Uri.parse('${widget.hubBaseUrl}/personalization'),
        headers: _headers,
      );
      _loadData();
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_isLoading) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }

    return Scaffold(
      appBar: AppBar(
        title: const Text('Personalization & Memory'),
        actions: [
          IconButton(icon: const Icon(Icons.delete_forever), onPressed: _resetAll, tooltip: 'Reset Everything'),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          SwitchListTile(
            title: const Text('Learn from Corrections'),
            subtitle: const Text('Suggest defaults when you repeatedly correct device targets'),
            value: _learningEnabled,
            onChanged: _toggleLearning,
          ),
          const Divider(),
          const Text('Remembered Facts', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
          if (_facts.isEmpty) const Padding(padding: EdgeInsets.all(8.0), child: Text('No facts remembered yet.')),
          ..._facts.map((f) => ListTile(
            title: Text(f['text'] ?? ''),
            subtitle: Text(f['created_at'] ?? ''),
            trailing: IconButton(icon: const Icon(Icons.delete_outline), onPressed: () => _deleteFact(f['id'])),
          )),
          const Divider(),
          const Text('Routines', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
          if (_routines.isEmpty) const Padding(padding: EdgeInsets.all(8.0), child: Text('No routines created.')),
          ..._routines.map((r) => ListTile(
            title: Text(r['name'] ?? ''),
            subtitle: Text('${(r['steps'] as List?)?.length ?? 0} steps'),
            trailing: IconButton(icon: const Icon(Icons.delete_outline), onPressed: () => _deleteRoutine(r['name'])),
          )),
        ],
      ),
    );
  }
}
