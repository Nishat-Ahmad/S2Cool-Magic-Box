# Static Model - Detailed Work Log

This file records exactly what was implemented to train XGBoost next-hour models (GHI and temperature) from the dataset in this folder.

## Scope completed

- Implemented and iteratively improved Static Model/train_xgboost.py.
- Built a working training pipeline end-to-end (load -> clean -> feature engineer -> train -> evaluate -> save artifacts).
- Added schema adapters so mixed Excel formats can be consumed by one script.
- Re-ran training after each major loader fix and regenerated artifacts.

## Detailed changes made in train_xgboost.py

### 1. Initial pipeline implementation

- Added CLI arguments:
  - --dataset-dir
  - --artifacts-dir
  - --max-rows-per-file
  - --max-files
  - --target-mode (ghi | temperature | both)
- Added chronological train/test split for time-series safe evaluation.
- Added XGBoost regressor training with fixed hyperparameters.
- Added artifact writers for model, metrics, predictions, and feature importance.

### 2. Robust column normalization and aliasing

- Added canonical column normalization function.
- Added aliases for heterogeneous names, including:
  - GHI_corr_Avg -> ghi
  - DNI_corr_Avg -> dni
  - DHI_corr_Avg -> dhi
  - Tair_Avg / Tamb -> temperature
  - RH_Avg / RH -> humidity
  - BP_CS100_Avg / BP -> pressure
  - WS / WSgust / WD -> wind features
  - TIMESTAMP / TS -> timestamp

### 3. Multi-format workbook ingestion strategies

- Added strategy-based reading for different file families:
  - TIMESTAMP style files (single-sheet layout)
  - Pk-Isb monthly workbooks (1h, 10min, day sheets; header around row 18)
- Added filename-pattern handling for both pk_isb_ and pk-isb_ variants.
- Added non-zip guard to skip invalid/corrupt files safely.

### 4. Canonical frame standardization

- Unified all loaded data into a canonical schema centered on timestamp plus weather/irradiance fields.
- Added numeric coercion and filtering to drop non-data rows (units/stat labels).
- Added source_file tagging for traceability.

### 5. Feature engineering implemented

- Calendar features: hour, day_of_year, month
- Cyclical features: hour_sin, hour_cos, doy_sin, doy_cos
- Lags: ghi_lag_1, ghi_lag_2, ghi_lag_3, ghi_lag_24, temp_lag_1
- Rolling: ghi_rolling_mean_3h, ghi_rolling_std_3h
- Targets:
  - target_ghi_next_1h
  - target_temperature_next_1h

## Artifact outputs

Generated in Static Model/artifacts:

- xgboost_ghi_model.joblib
  - Trained model used for inference.
- xgboost_ghi_metrics.json
  - Metrics and metadata for the latest run.
- xgboost_ghi_test_predictions.csv
  - Holdout actual/predicted/residual rows.
- xgboost_ghi_feature_importance.csv
  - Feature importance scores from the trained model.
- xgboost_temp_model.joblib
  - Trained temperature model for next-hour ambient temperature forecasting.
- xgboost_temp_metrics.json
  - Metrics and metadata for temperature target mode.
- xgboost_temp_test_predictions.csv
  - Holdout actual/predicted/residual rows for temperature mode.
- xgboost_temp_feature_importance.csv
  - Feature importance scores for temperature model.

## Target modes

- ghi
  - Predicts target_ghi_next_1h (next-hour GHI).
- temperature
  - Predicts target_temperature_next_1h (next-hour ambient temperature).
- both
  - Trains and saves both GHI and temperature models in one run.

## Training runs and outcomes

### Early baseline full run (before schema adapters)

- Files scanned: 80
- Usable files: 1
- Rows loaded: 438103
- Performance:
  - MAE: 18.2070
  - RMSE: 45.7878
  - R2: 0.9744

### After schema-adapter upgrades

- Loader validation (max_rows_per_file=1500):
  - Usable files: 79 of 80
  - Rows loaded: 28368
- Updated training run (max_rows_per_file=1500):
  - train_rows: 21476
  - test_rows: 5370
  - MAE: 25.5479779484
  - RMSE: 57.3322516269
  - R2: 0.9582070276

### Latest full training pass (target-mode=both, full dataset)

Run command:

```powershell
C:\Users\Droid\AppData\Local\Python\pythoncore-3.14-64\python.exe "d:/Code/S2Cool-Magic-Box/Static Model/train_xgboost.py" --target-mode both --max-rows-per-file 0 --max-files 0
```

Run summary:

- Files scanned: 80
- Usable files: 79
- Skipped files: 1
- Total rows loaded: 608006

GHI model metrics:

- train_rows: 346113
- test_rows: 86529
- MAE: 17.1705728591
- RMSE: 44.9622737444
- R2: 0.9752908990

Temperature model metrics:

- train_rows: 346113
- test_rows: 86529
- MAE: 0.2810751686
- RMSE: 0.5017530721
- R2: 0.9963254656

## Remaining known issue

- One dataset file is structurally invalid and still skipped:
  - Static Model/Dataset/Pk-Isb_2020-01-Mar-to-15-Dec.xlsx
  - Reason: not a valid zip-based xlsx container.

## Current status

- The pipeline now ingests nearly all files in this dataset automatically.
- Artifacts are generated successfully.
- The script is ready for larger/full-row runs by setting --max-rows-per-file 0.

## Recent temperature mode validation

Run command:

```powershell
C:\Users\Droid\AppData\Local\Python\pythoncore-3.14-64\python.exe "d:/Code/S2Cool-Magic-Box/Static Model/train_xgboost.py" --target-mode temperature --max-rows-per-file 1000 --max-files 20
```

Latest temp metrics:

- train_rows: 8912
- test_rows: 2228
- MAE: 0.2982
- RMSE: 0.6787
- R2: 0.9818

## API-based holdout evaluation on 2026 Islamabad data

Run command:

```powershell
py -3.14 "scripts/train_xgboost.py" --dataset-dir "dataset" --target-mode "both" --backtest-mode "holdout" --test-source "api" --api-city "Islamabad" --api-start-date "2026-01-01" --api-end-date "2026-03-01" --max-rows-per-file 1500 --artifacts-dir "artifacts"
```

Execution summary:

- Dataset source: local Excel files (79/80 usable files)
- Dataset rows loaded: 28,368 (capped at max-rows-per-file=1500)
- Test data source: Open-Meteo API, Islamabad, 2026-01-01 to 2026-03-01
- Test rows fetched: 1,440 hourly records, processed to 1,439 (after feature engineering)

**GHI model results:**

- train_rows: 26,846
- test_rows: 1,439
- test_descriptor: api:Islamabad:2026-01-01->2026-03-01
- MAE: 56.4147
- RMSE: 86.2981
- R2: 0.8278

**Temperature model results:**

- train_rows: 26,846
- test_rows: 1,439
- test_descriptor: api:Islamabad:2026-01-01->2026-03-01
- MAE: 1.1252
- RMSE: 1.5487
- R2: 0.9078

This run demonstrates the model's ability to forecast next-hour conditions on external, real-world 2026 weather data from an API source, validating generalization performance beyond the static training dataset.
