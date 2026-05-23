# Diagnosis Workflow

This workflow reduces manual spread repair work without removing the human
review step.

## Phases

1. Open one PDF volume.
2. Open the `Diagnose` tab.
3. Run `Run Cross-Page Scan` or import an `adjacent_clusters.csv` file from
   `manga-spread-continuity`.
4. Review each candidate visually in the main preview and mark it true or false.
5. Use `Add Missing Spread...` for true spreads that did not appear in the scan.
6. Click `Check Damage Against Current Layout`.
7. Run `Run Insert-Point Scoring` or import a `gaps.csv` file from
   `manga-insert-point-scorer`.
8. Review green and red spine markers.
9. Select one suggested insert row and click `Insert Selected Blank`.
10. Click `Recheck Layout` before deciding on another insertion.

## Manual Gates

The GUI never performs scan, damage check, scoring, and insertion as one chained
operation. Scan results are candidates. Insert scores are suggestions. Only a
user click changes the layout.

## Apple Books Cover Gap

The damage check uses the current `Preview Apple Books cover gap` checkbox. This
matters because Apple Books can place a virtual blank page beside the cover and
shift every following pair. A spread such as `037-038` can be intact with the
flag off and damaged with the flag on.

## Marker Meaning

Green `insert +score` markers show one-blank insertion points that repair one or
more damaged confirmed spreads and do not break currently intact confirmed
spreads.

Red `protected` markers show gaps inside confirmed spreads or gaps where a blank
would break an intact confirmed spread.

## Prototype Outputs

The spread scan consumes `adjacent_clusters.csv` from `manga-spread-continuity`.
The insert review consumes `gaps.csv` from `manga-insert-point-scorer`.
