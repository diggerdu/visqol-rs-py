# ViSQOL Native Python Bindings

Native Rust Python bindings for ViSQOL (Virtual Speech Quality Objective Listener) audio quality assessment.

## Features

- **Native Performance**: Direct Rust implementation without subprocess overhead
- **Numpy Integration**: Direct numpy array processing
- **Python Lists Support**: Can also process Python lists of floats
- **Speech & Audio Modes**: Supports both speech (16kHz) and audio (48kHz) modes
- **Memory Efficient**: No temporary file creation required

## Installation

```bash
pip install maturin
maturin develop --release
```

## Usage

```python
import numpy as np
import visqol_native

# Create calculator in speech mode (optimized for 16kHz speech)
calculator = visqol_native.VisqolCalculator.speech_mode()

# Or audio mode (optimized for 48kHz general audio)
# calculator = visqol_native.VisqolCalculator.audio_mode()

# Prepare audio data (1D arrays, values in [-1.0, 1.0] range)
sample_rate = 48000
duration = 3.0
t = np.linspace(0, duration, int(sample_rate * duration))

reference_audio = 0.5 * np.sin(2 * np.pi * 440 * t)
degraded_audio = reference_audio + 0.1 * np.random.randn(len(reference_audio))

# Calculate ViSQOL score
result = calculator.calculate(
    reference_audio=reference_audio,
    degraded_audio=degraded_audio,
    sample_rate=sample_rate
)

print(f"MOS-LQO: {result.moslqo:.3f}")
print(f"Processing time: {result.processing_time:.3f}s")
```

## API Reference

### VisqolCalculator

- `VisqolCalculator.speech_mode()`: Create calculator optimized for speech (16kHz)
- `VisqolCalculator.audio_mode(model_path=None)`: Create calculator for general audio (48kHz)
- `calculate(reference_audio, degraded_audio, sample_rate)`: Calculate ViSQOL score for numpy arrays
- `calculate_from_lists(reference_audio, degraded_audio, sample_rate)`: Calculate for Python lists

### SimilarityResult

- `moslqo`: Mean Opinion Score - Listening Quality Objective
- `similarity_score`: Internal similarity score (optional)
- `processing_time`: Time taken for calculation in seconds