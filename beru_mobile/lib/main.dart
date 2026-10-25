import 'package:flutter/material.dart';
import 'settings/personalization_screen.dart';

void main() {
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
  String _assistantState = 'Idle';
  bool _isListening = false;
  String _lastTranscript = '';

  void _toggleListening() {
    setState(() {
      _isListening = !_isListening;
      _assistantState = _isListening ? 'Listening...' : 'Idle';
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Beru Assistant'),
        actions: [
          IconButton(
            icon: const Icon(Icons.settings),
            onPressed: () {
              Navigator.of(context).push(
                MaterialPageRoute(
                  builder: (ctx) => const PersonalizationScreen(
                    hubBaseUrl: 'http://localhost:8000',
                    deviceToken: '',
                  ),
                ),
              );
            },
          ),
        ],
      ),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(24.0),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Container(
                width: 140,
                height: 140,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: _isListening
                      ? Theme.of(context).colorScheme.primaryContainer
                      : Colors.grey.shade900,
                  boxShadow: _isListening
                      ? [
                          BoxShadow(
                            color: Theme.of(context).colorScheme.primary.withAlpha(128),
                            blurRadius: 24,
                            spreadRadius: 8,
                          ),
                        ]
                      : [],
                ),
                child: Icon(
                  _isListening ? Icons.mic : Icons.mic_none,
                  size: 64,
                  color: _isListening
                      ? Theme.of(context).colorScheme.primary
                      : Colors.grey,
                ),
              ),
              const SizedBox(height: 32),
              Text(
                _assistantState,
                style: Theme.of(context).textTheme.headlineMedium,
              ),
              const SizedBox(height: 8),
              Text(
                'Wake phrase: "Hey Beru"',
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: Colors.grey,
                    ),
              ),
              if (_lastTranscript.isNotEmpty) ...[
                const SizedBox(height: 24),
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(16.0),
                    child: Text(_lastTranscript),
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
      floatingActionButton: FloatingActionButton.large(
        onPressed: _toggleListening,
        tooltip: 'Speak to Beru',
        child: Icon(_isListening ? Icons.stop : Icons.mic),
      ),
      floatingActionButtonLocation: FloatingActionButtonLocation.centerFloat,
    );
  }
}
