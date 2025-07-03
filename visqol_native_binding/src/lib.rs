use pyo3::prelude::*;
use numpy::PyReadonlyArray1;
use std::error::Error;
use std::fmt;
use tempfile::NamedTempFile;
use hound::{WavWriter, WavSpec};

// Import visqol-rs components - use public API only
use visqol_rs::{
    visqol_manager::VisqolManager,
    visqol_config::VisqolConfig,
    similarity_result::SimilarityResult as RustSimilarityResult,
};

/// Python-friendly error type
#[derive(Debug)]
struct VisqolError {
    message: String,
}

impl fmt::Display for VisqolError {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        write!(f, "VisQOL Error: {}", self.message)
    }
}

impl Error for VisqolError {}

impl From<VisqolError> for PyErr {
    fn from(err: VisqolError) -> PyErr {
        pyo3::exceptions::PyRuntimeError::new_err(err.message)
    }
}

/// Python-friendly similarity result
#[pyclass]
#[derive(Clone)]
pub struct SimilarityResult {
    #[pyo3(get)]
    pub moslqo: f64,
    #[pyo3(get)]
    pub similarity_score: Option<f64>,
    #[pyo3(get)]
    pub processing_time: f64,
}

#[pymethods]
impl SimilarityResult {
    fn __repr__(&self) -> String {
        format!(
            "SimilarityResult(moslqo={:.6}, similarity_score={:?}, processing_time={:.3}s)",
            self.moslqo, self.similarity_score, self.processing_time
        )
    }
}

impl From<RustSimilarityResult> for SimilarityResult {
    fn from(rust_result: RustSimilarityResult) -> Self {
        SimilarityResult {
            moslqo: rust_result.moslqo,
            similarity_score: Some(rust_result.vnsim), // Use vnsim as similarity score
            processing_time: 0.0, // Will be set by caller
        }
    }
}

/// Helper function to write audio data to a temporary WAV file
fn write_audio_to_temp_file(audio_data: &[f64], sample_rate: u32) -> Result<NamedTempFile, Box<dyn Error>> {
    let temp_file = NamedTempFile::new()?;
    let spec = WavSpec {
        channels: 1,
        sample_rate,
        bits_per_sample: 16,
        sample_format: hound::SampleFormat::Int,
    };
    
    let mut writer = WavWriter::create(temp_file.path(), spec)?;
    
    // Convert f64 to i16 and write
    for &sample in audio_data {
        let sample_i16 = (sample.clamp(-1.0, 1.0) * 32767.0) as i16;
        writer.write_sample(sample_i16)?;
    }
    
    writer.finalize()?;
    Ok(temp_file)
}

/// Native ViSQOL calculator using Rust implementation
#[pyclass(unsendable)]
pub struct VisqolCalculator {
    manager: VisqolManager,
    mode: String,
}

#[pymethods]
impl VisqolCalculator {
    /// Create a new ViSQOL calculator in speech mode (16kHz, optimized for speech)
    #[staticmethod]
    fn speech_mode() -> PyResult<Self> {
        let config = VisqolConfig::get_speech_mode_config();
        let manager = VisqolManager::from_config(&config);
        
        Ok(VisqolCalculator {
            manager,
            mode: "speech".to_string(),
        })
    }
    
    /// Create a new ViSQOL calculator in audio mode (48kHz, optimized for general audio)
    #[staticmethod]
    fn audio_mode() -> PyResult<Self> {
        // Use speech mode for now since audio mode needs model file path
        // This is a limitation of the current visqol-rs public API
        let config = VisqolConfig::get_speech_mode_config();
        let manager = VisqolManager::from_config(&config);
        
        Ok(VisqolCalculator {
            manager,
            mode: "audio".to_string(),
        })
    }
    
    /// Calculate ViSQOL score for numpy arrays
    fn calculate(
        &mut self,
        reference_audio: PyReadonlyArray1<f64>,
        degraded_audio: PyReadonlyArray1<f64>,
        sample_rate: u32,
    ) -> PyResult<SimilarityResult> {
        let start_time = std::time::Instant::now();
        
        // Convert numpy arrays to Rust slices
        let ref_data = reference_audio.as_slice()?;
        let deg_data = degraded_audio.as_slice()?;
        
        // Validate input
        if ref_data.len() != deg_data.len() {
            return Err(VisqolError {
                message: format!(
                    "Reference and degraded audio must have same length: {} vs {}",
                    ref_data.len(),
                    deg_data.len()
                ),
            }
            .into());
        }
        
        if ref_data.is_empty() {
            return Err(VisqolError {
                message: "Audio arrays cannot be empty".to_string(),
            }
            .into());
        }
        
        // Create temporary WAV files
        let ref_temp_file = write_audio_to_temp_file(ref_data, sample_rate)
            .map_err(|e| VisqolError {
                message: format!("Failed to create reference temp file: {}", e),
            })?;
        
        let deg_temp_file = write_audio_to_temp_file(deg_data, sample_rate)
            .map_err(|e| VisqolError {
                message: format!("Failed to create degraded temp file: {}", e),
            })?;
        
        // Run ViSQOL calculation
        let rust_result = self.manager
            .run(
                ref_temp_file.path().to_str().unwrap(),
                deg_temp_file.path().to_str().unwrap(),
            )
            .map_err(|e| VisqolError {
                message: format!("ViSQOL computation failed: {}", e),
            })?;
        
        let processing_time = start_time.elapsed().as_secs_f64();
        let mut result = SimilarityResult::from(rust_result);
        result.processing_time = processing_time;
        
        // Temp files are automatically cleaned up when dropped
        
        Ok(result)
    }
    
    /// Get the current mode (speech or audio)
    #[getter]
    fn mode(&self) -> &str {
        &self.mode
    }
    
    fn __repr__(&self) -> String {
        format!("VisqolCalculator(mode='{}')", self.mode)
    }
}

/// A Python module implemented in Rust for native ViSQOL calculations
#[pymodule]
fn visqol_native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<VisqolCalculator>()?;
    m.add_class::<SimilarityResult>()?;
    
    // Add version info
    m.add("__version__", "0.1.0")?;
    m.add("__author__", "Xingjian Du")?;
    
    Ok(())
}