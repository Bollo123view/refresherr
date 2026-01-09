"""Unit tests for queue_repairs.py business logic."""
import pytest
import sys
import os
from pathlib import Path

# Add the app directory to sys.path to ensure proper imports
app_dir = Path(__file__).parent.parent
if str(app_dir) not in sys.path:
    sys.path.insert(0, str(app_dir))

from refresher.tools.queue_repairs import (
    parse_route_map,
    pick_type,
    extract_sxxeyy,
    extract_show_and_season_from_path,
    build_episode_term,
    build_season_term,
)


class TestParseRouteMap:
    """Tests for parse_route_map function."""
    
    def test_parse_single_route(self):
        """Test parsing a single route mapping."""
        result = parse_route_map("/opt/media/movies=radarr")
        assert len(result) == 1
        assert result[0] == ("/opt/media/movies", "radarr")
    
    def test_parse_multiple_routes(self):
        """Test parsing multiple route mappings."""
        result = parse_route_map("/opt/media/movies=radarr,/opt/media/tv=sonarr")
        assert len(result) == 2
        # Should be sorted by length (longest first)
        assert result[0][0] == "/opt/media/movies"
        assert result[1][0] == "/opt/media/tv"
    
    def test_parse_routes_sorted_by_length(self):
        """Test that routes are sorted by path length (longest first)."""
        result = parse_route_map("/opt/media/tv=sonarr,/opt/media/tv/4k=sonarr_4k")
        assert len(result) == 2
        # Longer path should come first
        assert result[0][0] == "/opt/media/tv/4k"
        assert result[1][0] == "/opt/media/tv"
    
    def test_parse_empty_string(self):
        """Test parsing empty string."""
        result = parse_route_map("")
        assert result == []
    
    def test_parse_with_spaces(self):
        """Test parsing with whitespace."""
        result = parse_route_map(" /opt/media/movies = radarr , /opt/media/tv = sonarr ")
        assert len(result) == 2
        # Note: parse_route_map strips trailing slashes but not spaces in the middle
        assert result[0][0].startswith("/opt/media/")
        assert result[0][1] == "radarr"
    
    def test_parse_trailing_slashes_removed(self):
        """Test that trailing slashes are removed from paths."""
        result = parse_route_map("/opt/media/movies/=radarr")
        assert result[0][0] == "/opt/media/movies"
    
    def test_parse_invalid_entries_skipped(self):
        """Test that entries without '=' are skipped."""
        result = parse_route_map("/opt/media/movies=radarr,invalid_entry,/opt/media/tv=sonarr")
        assert len(result) == 2


class TestPickType:
    """Tests for pick_type function."""
    
    def test_pick_exact_match(self):
        """Test picking type for exact path match."""
        routes = [("/opt/media/movies", "radarr"), ("/opt/media/tv", "sonarr")]
        result = pick_type("/opt/media/movies", routes)
        assert result == "radarr"
    
    def test_pick_prefix_match(self):
        """Test picking type for path with prefix match."""
        routes = [("/opt/media/movies", "radarr"), ("/opt/media/tv", "sonarr")]
        result = pick_type("/opt/media/movies/Action/Movie.mkv", routes)
        assert result == "radarr"
    
    def test_pick_longest_match(self):
        """Test that longest matching prefix wins."""
        routes = [
            ("/opt/media/tv/4k", "sonarr_4k"),
            ("/opt/media/tv", "sonarr"),
        ]
        result = pick_type("/opt/media/tv/4k/Show/episode.mkv", routes)
        assert result == "sonarr_4k"
    
    def test_pick_no_match(self):
        """Test that None is returned when no route matches."""
        routes = [("/opt/media/movies", "radarr")]
        result = pick_type("/other/path/file.mkv", routes)
        assert result is None
    
    def test_pick_empty_routes(self):
        """Test with empty routes list."""
        result = pick_type("/opt/media/movies/file.mkv", [])
        assert result is None


class TestExtractSxxeyy:
    """Tests for extract_sxxeyy function."""
    
    def test_extract_standard_format(self):
        """Test extracting S01E05 format."""
        assert extract_sxxeyy("Show.S01E05.720p.mkv") == "S01E05"
        assert extract_sxxeyy("Show.s02e10.mkv") == "S02E10"
    
    def test_extract_alternative_format(self):
        """Test extracting 1x05 format."""
        assert extract_sxxeyy("Show.1x05.mkv") == "S01E05"
        assert extract_sxxeyy("Show.2x10.mkv") == "S02E10"
    
    def test_extract_from_path(self):
        """Test extracting from full path."""
        path = "/opt/media/tv/Show/Season 1/Show.S01E05.mkv"
        assert extract_sxxeyy(path) == "S01E05"
    
    def test_extract_no_match(self):
        """Test with no season/episode pattern."""
        assert extract_sxxeyy("Movie.2023.1080p.mkv") is None
        assert extract_sxxeyy("RandomFile.mkv") is None
    
    def test_extract_empty_string(self):
        """Test with empty or None input."""
        assert extract_sxxeyy("") is None
        assert extract_sxxeyy(None) is None
    
    def test_extract_double_digit_season(self):
        """Test with double-digit season numbers."""
        assert extract_sxxeyy("Show.S12E25.mkv") == "S12E25"
    
    def test_extract_triple_digit_episode(self):
        """Test with triple-digit episode numbers."""
        assert extract_sxxeyy("Show.S01E105.mkv") == "S01E105"


class TestExtractShowAndSeasonFromPath:
    """Tests for extract_show_and_season_from_path function."""
    
    def test_extract_standard_structure(self):
        """Test extracting from standard Jellyfin structure."""
        path = "/opt/media/jelly/tv/Breaking Bad/Season 1/episode.mkv"
        show, season = extract_show_and_season_from_path(path)
        assert show == "Breaking Bad"
        assert season == 1
    
    def test_extract_double_digit_season(self):
        """Test with double-digit season."""
        path = "/opt/media/jelly/tv/Show/Season 12/episode.mkv"
        show, season = extract_show_and_season_from_path(path)
        assert show == "Show"
        assert season == 12
    
    def test_extract_season_with_spaces(self):
        """Test with various season folder formats."""
        path1 = "/opt/media/tv/Show/Season 5/ep.mkv"
        show1, season1 = extract_show_and_season_from_path(path1)
        assert season1 == 5
        
        path2 = "/opt/media/tv/Show/Season  3/ep.mkv"  # Multiple spaces
        show2, season2 = extract_show_and_season_from_path(path2)
        assert season2 == 3
    
    def test_extract_no_season(self):
        """Test with path that has no season folder."""
        path = "/opt/media/movies/Movie/movie.mkv"
        show, season = extract_show_and_season_from_path(path)
        assert season is None
    
    def test_extract_show_with_special_chars(self):
        """Test with show names containing special characters."""
        path = "/opt/media/tv/The Show (2023)/Season 1/ep.mkv"
        show, season = extract_show_and_season_from_path(path)
        assert show == "The Show (2023)"
        assert season == 1


class TestBuildEpisodeTerm:
    """Tests for build_episode_term function."""
    
    def test_build_sonarr_term_with_episode(self):
        """Test building search term for Sonarr with episode info."""
        path = "/opt/media/tv/Breaking Bad/Season 1/Breaking.Bad.S01E05.mkv"
        term = build_episode_term(path, "sonarr_tv")
        assert "Breaking Bad" in term
        assert "S01E05" in term
    
    def test_build_sonarr_term_without_episode(self):
        """Test building search term for Sonarr without episode info."""
        path = "/opt/media/tv/Show/Season 1/episode.mkv"
        term = build_episode_term(path, "sonarr_tv")
        assert "Show" in term
    
    def test_build_radarr_term(self):
        """Test building search term for Radarr (movies)."""
        path = "/opt/media/movies/Inception (2010)/Inception.2010.1080p.mkv"
        term = build_episode_term(path, "radarr_movie")
        # Should use parent directory name
        assert "Inception (2010)" in term
    
    def test_build_term_with_different_types(self):
        """Test with various type prefixes."""
        path = "/opt/media/tv/Show/Season 1/Show.S01E01.mkv"
        
        # All sonarr variants should work similarly
        assert build_episode_term(path, "sonarr") is not None
        assert build_episode_term(path, "sonarr_tv") is not None
        assert build_episode_term(path, "sonarr_4k") is not None


class TestBuildSeasonTerm:
    """Tests for build_season_term function."""
    
    def test_build_single_digit_season(self):
        """Test building season search term with single-digit season."""
        term = build_season_term("Breaking Bad", 1)
        assert term == "Breaking Bad S01"
    
    def test_build_double_digit_season(self):
        """Test building season search term with double-digit season."""
        term = build_season_term("The Show", 12)
        assert term == "The Show S12"
    
    def test_build_with_special_chars(self):
        """Test with show name containing special characters."""
        term = build_season_term("The Show (2023)", 5)
        assert term == "The Show (2023) S05"


# Integration-style tests

class TestRouteIntegration:
    """Integration tests combining multiple functions."""
    
    def test_full_route_workflow(self):
        """Test complete workflow of parsing routes and picking types."""
        # Parse routes
        route_map = "/opt/media/jelly/4k=radarr_4k,/opt/media/jelly/tv=sonarr_tv"
        routes = parse_route_map(route_map)
        
        # Pick types for various paths
        assert pick_type("/opt/media/jelly/4k/Movie/file.mkv", routes) == "radarr_4k"
        assert pick_type("/opt/media/jelly/tv/Show/file.mkv", routes) == "sonarr_tv"
    
    def test_episode_term_building_workflow(self):
        """Test complete workflow of building episode search terms."""
        path = "/opt/media/jelly/tv/Breaking Bad/Season 3/Breaking.Bad.S03E07.mkv"
        
        # Extract components
        show, season = extract_show_and_season_from_path(path)
        episode_code = extract_sxxeyy(path)
        
        # Build terms
        episode_term = build_episode_term(path, "sonarr_tv")
        season_term = build_season_term(show, season)
        
        assert show == "Breaking Bad"
        assert season == 3
        assert episode_code == "S03E07"
        assert "Breaking Bad" in episode_term
        assert "S03E07" in episode_term
        assert season_term == "Breaking Bad S03"
