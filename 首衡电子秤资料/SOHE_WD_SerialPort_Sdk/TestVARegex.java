import java.util.regex.Pattern;
import java.util.regex.Matcher;

public class TestVARegex {
    public static void main(String[] args) {
        // Actual received data
        String actualData = "VA,01,28,S,N,-   1.820,   0.000 kg";
        
        // Current regex pattern
        Pattern currentPattern = Pattern.compile(
            "^VA,([0-9]{1,3}),([0-9]{2}),([SUO]),([NG]),([\\+\\-])\\s+([0-9\\.]+),\\s+([0-9\\.]+)\\s+(kg|g|lb|oz)\\s*\\r?\\n?$", 
            Pattern.CASE_INSENSITIVE
        );
        
        System.out.println("Test data: '" + actualData + "'");
        System.out.println("Data length: " + actualData.length());
        
        // Show detailed character information
        System.out.println("\nCharacter analysis:");
        for (int i = 0; i < actualData.length(); i++) {
            char c = actualData.charAt(i);
            System.out.printf("Position %2d: '%c' (ASCII: %d, Hex: %02X)\n", i, c, (int)c, (int)c);
        }
        
        System.out.println("\nCurrent regex test:");
        Matcher matcher = currentPattern.matcher(actualData);
        System.out.println("Match result: " + matcher.matches());
        
        if (matcher.matches()) {
            System.out.println("Match successful!");
            for (int i = 1; i <= matcher.groupCount(); i++) {
                System.out.println("Group " + i + ": '" + matcher.group(i) + "'");
            }
        } else {
            System.out.println("Match failed!");
            
            // Try different regex variants
            System.out.println("\nTrying other regex variants:");
            
            // Variant 1: More flexible space matching
            Pattern pattern1 = Pattern.compile(
                "^VA,([0-9]{1,3}),([0-9]{2}),([SUO]),([NG]),([\\+\\-])\\s*([0-9\\.]+),\\s*([0-9\\.]+)\\s*(kg|g|lb|oz)\\s*$", 
                Pattern.CASE_INSENSITIVE
            );
            System.out.println("Variant 1 (\\s*): " + pattern1.matcher(actualData).matches());
            
            // Variant 2: Exact space count matching
            Pattern pattern2 = Pattern.compile(
                "^VA,([0-9]{1,3}),([0-9]{2}),([SUO]),([NG]),([\\+\\-])   ([0-9\\.]+),   ([0-9\\.]+) (kg|g|lb|oz)$", 
                Pattern.CASE_INSENSITIVE
            );
            System.out.println("Variant 2 (exact 3 spaces): " + pattern2.matcher(actualData).matches());
            
            // Variant 3: Mixed space matching
            Pattern pattern3 = Pattern.compile(
                "^VA,([0-9]{1,3}),([0-9]{2}),([SUO]),([NG]),([\\+\\-])\\s{1,5}([0-9\\.]+),\\s{1,5}([0-9\\.]+)\\s+(kg|g|lb|oz)$", 
                Pattern.CASE_INSENSITIVE
            );
            System.out.println("Variant 3 (1-5 spaces): " + pattern3.matcher(actualData).matches());
            
            // Variant 4: Remove line end anchors
            Pattern pattern4 = Pattern.compile(
                "VA,([0-9]{1,3}),([0-9]{2}),([SUO]),([NG]),([\\+\\-])\\s+([0-9\\.]+),\\s+([0-9\\.]+)\\s+(kg|g|lb|oz)", 
                Pattern.CASE_INSENSITIVE
            );
            System.out.println("Variant 4 (no ^$): " + pattern4.matcher(actualData).matches());
            
            // Test simplest match
            if (pattern4.matcher(actualData).matches()) {
                Matcher m = pattern4.matcher(actualData);
                m.matches();
                System.out.println("Variant 4 match successful! Group info:");
                for (int i = 1; i <= m.groupCount(); i++) {
                    System.out.println("Group " + i + ": '" + m.group(i) + "'");
                }
            }
        }
    }
}