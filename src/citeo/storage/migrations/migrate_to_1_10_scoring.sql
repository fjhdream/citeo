-- Migration: Update scoring system from 0-1 to 1-10 scale
-- This migration updates existing relevance_score values to the new 1-10 scale

-- Update existing scores from 0-1 range to 1-10 range
-- Reason: Convert old 0-1 scores to new 1-10 scale by multiplying by 9 and adding 1
-- Formula: new_score = old_score * 9 + 1
-- Examples: 0.0 -> 1.0, 0.5 -> 5.5, 0.8 -> 8.2, 1.0 -> 10.0
UPDATE papers
SET relevance_score = (relevance_score * 9.0) + 1.0
WHERE relevance_score >= 0.0 AND relevance_score <= 1.0;

-- Note: Papers that haven't been processed yet (relevance_score = 0.0)
-- will be updated to 1.0, which is the new default minimum score
